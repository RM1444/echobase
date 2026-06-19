"""Shared AT-SPI accessibility helpers.

These were originally inlined inside individual plugins (``labels.py`` walked the
accessibility tree for clickable controls; ``dictation.py`` inserted text into the
focused field). They are now centralised here so several features can reuse them:

  * :func:`get_clickables` — every clickable control in the active window, with
    screen geometry. Used by ``labels`` (numbered hints), ``browser`` (link
    clicking), ``click_by_name`` and head-tracking snap-to-button.
  * :func:`insert_text` — type text into the focused editable. Used by dictation,
    the browser address bar, and personal text snippets.
  * :func:`read_window_text` — gather the visible text of the active window. Used
    by "read the screen" out loud.

Every query runs the AT-SPI work in a short-lived ``python3 -c`` subprocess, so a
flaky toolkit accessibility bridge can stall or crash without taking down the
assistant (the parent just sees an empty result after the timeout).
"""

import json
import subprocess

from . import ui

MAX_HINTS = 60

# Walk the AT-SPI tree of the active top-level window and print a JSON list of
# clickable elements with screen geometry, name and role. Runs out-of-process.
_CLICKABLES_SCRIPT = (
    r"""
import gi, json, sys
gi.require_version('Atspi', '2.0')
from gi.repository import Atspi

# Bound each AT-SPI/D-Bus call: a single slow or wedged toolkit reply fails fast
# instead of stalling the whole walk until the parent's hard timeout kills us.
try:
    Atspi.set_timeout(800, 3000)
except Exception:
    pass

R = Atspi.Role
CLICK_ROLES = {}
for name in [
    'PUSH_BUTTON', 'TOGGLE_BUTTON', 'CHECK_BOX', 'RADIO_BUTTON', 'MENU_ITEM',
    'CHECK_MENU_ITEM', 'RADIO_MENU_ITEM', 'MENU', 'LINK', 'LIST_ITEM',
    'PAGE_TAB', 'TAB', 'COMBO_BOX', 'ENTRY', 'PASSWORD_TEXT', 'SPIN_BUTTON',
    'SLIDER', 'TABLE_CELL', 'ICON', 'PUSH_BUTTON_MENU',
]:
    r = getattr(R, name, None)
    if r is not None:
        CLICK_ROLES[r] = name

MAX = %d
MAX_DEPTH = 25
MAX_VISITS = 4000  # hard ceiling on nodes touched, so a huge tree can't hang us
out = []
visits = [0]

def extents(obj):
    try:
        e = obj.get_extents(Atspi.CoordType.SCREEN)
        return e.x, e.y, e.width, e.height
    except Exception:
        return None

def walk(obj, depth, screen_w, screen_h):
    if depth > MAX_DEPTH or len(out) >= MAX or visits[0] >= MAX_VISITS:
        return
    visits[0] += 1
    # One state-set fetch per node (reused below), rather than two.
    try:
        st = obj.get_state_set()
        showing = st.contains(Atspi.StateType.SHOWING)
    except Exception:
        return
    # Prune hidden/offscreen subtrees: their descendants can't be clicked, and
    # descending into them (e.g. background browser tabs, collapsed panels) is
    # what turns this walk into thousands of round-trips and times it out. The
    # active top-level frame (depth 0) is always walked.
    if depth > 0 and not showing:
        return
    try:
        clickable = (
            showing
            and st.contains(Atspi.StateType.VISIBLE)
            and not st.contains(Atspi.StateType.DEFUNCT)
            and obj.get_role() in CLICK_ROLES
        )
    except Exception:
        clickable = False
    if clickable:
        ext = extents(obj)
        if ext:
            x, y, w, h = ext
            if 0 < w < screen_w and 0 < h < screen_h and x >= 0 and y >= 0:
                try:
                    name = obj.get_name() or ''
                except Exception:
                    name = ''
                out.append({
                    'x': x, 'y': y, 'w': w, 'h': h,
                    'name': name[:60],
                    'role': CLICK_ROLES.get(obj.get_role(), ''),
                })
    try:
        n = obj.get_child_count()
    except Exception:
        return
    for i in range(n):
        if len(out) >= MAX or visits[0] >= MAX_VISITS:
            break
        try:
            child = obj.get_child_at_index(i)
        except Exception:
            continue
        if child is not None:
            walk(child, depth + 1, screen_w, screen_h)

desktop = Atspi.get_desktop(0)
for i in range(desktop.get_child_count()):
    try:
        app = desktop.get_child_at_index(i)
    except Exception:
        continue
    if app is None:
        continue
    for j in range(app.get_child_count()):
        try:
            frame = app.get_child_at_index(j)
        except Exception:
            continue
        if frame is None:
            continue
        try:
            active = frame.get_state_set().contains(Atspi.StateType.ACTIVE)
        except Exception:
            active = False
        if active:
            walk(frame, 0, 100000, 100000)

print(json.dumps(out))
"""
    % MAX_HINTS
)

# Insert text into the currently-focused editable element. ``backspace`` (chr 8)
# deletes the char before the caret. The text is passed as argv[1].
_INSERT_SCRIPT = r"""
import gi, sys
gi.require_version('Atspi', '2.0')
from gi.repository import Atspi

try:
    Atspi.set_timeout(800, 3000)
except Exception:
    pass

text = sys.argv[1] if len(sys.argv) > 1 else ""

def find_focused_editable(obj, depth=0):
    if depth > 25:
        return None
    try:
        state = obj.get_state_set()
        if state.contains(Atspi.StateType.FOCUSED) and state.contains(Atspi.StateType.EDITABLE):
            return obj
        for i in range(obj.get_child_count()):
            result = find_focused_editable(obj.get_child_at_index(i), depth + 1)
            if result:
                return result
    except Exception:
        pass
    return None

desktop = Atspi.get_desktop(0)
for i in range(desktop.get_child_count()):
    app = desktop.get_child_at_index(i)
    result = find_focused_editable(app)
    if result:
        try:
            pos = result.get_caret_offset()
        except Exception:
            pos = -1
        for char in text:
            if char == chr(8):  # backspace
                if pos > 0:
                    result.delete_text(pos - 1, pos)
                    pos -= 1
            else:
                result.insert_text(pos, char, len(char.encode('utf-8')))
                pos += 1
        print("OK")
        sys.exit(0)

print("NO_FOCUS")
"""

# Gather visible text from the active top-level window: any element exposing the
# AT-SPI Text interface, in tree order, de-duplicated against the running output.
_READ_SCRIPT = r"""
import gi, sys
gi.require_version('Atspi', '2.0')
from gi.repository import Atspi

try:
    Atspi.set_timeout(800, 3000)
except Exception:
    pass

MAX_VISITS = 4000
parts = []
visits = [0]

def grab_text(obj):
    try:
        txt = Atspi.Text.get_text(obj, 0, Atspi.Text.get_character_count(obj))
    except Exception:
        txt = None
    if not txt:
        try:
            txt = obj.get_name()
        except Exception:
            txt = None
    if txt:
        txt = txt.strip()
        if txt and (not parts or parts[-1] != txt):
            parts.append(txt)

def walk(obj, depth=0):
    if depth > 30 or len(parts) > 400 or visits[0] >= MAX_VISITS:
        return
    visits[0] += 1
    # Skip hidden/offscreen subtrees (depth > 0) so reading the active window
    # doesn't crawl every collapsed panel or background view and time out.
    try:
        if depth > 0 and not obj.get_state_set().contains(Atspi.StateType.SHOWING):
            return
    except Exception:
        return
    try:
        grab_text(obj)
        for i in range(obj.get_child_count()):
            if visits[0] >= MAX_VISITS:
                break
            child = obj.get_child_at_index(i)
            if child is not None:
                walk(child, depth + 1)
    except Exception:
        pass

desktop = Atspi.get_desktop(0)
for i in range(desktop.get_child_count()):
    try:
        app = desktop.get_child_at_index(i)
    except Exception:
        continue
    if app is None:
        continue
    for j in range(app.get_child_count()):
        try:
            frame = app.get_child_at_index(j)
            active = frame.get_state_set().contains(Atspi.StateType.ACTIVE)
        except Exception:
            active = False
        if active:
            walk(frame)

print("\n".join(parts))
"""


def _run_script(script, *args, timeout=8, tag="atspi"):
    """Run an AT-SPI helper script out-of-process. Returns stdout (str) or ""."""
    try:
        result = subprocess.run(
            ["python3", "-c", script, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        ui.log("error", f"{tag} · accessibility query failed ({e})", ui.RED)
        return ""
    out = (result.stdout or "").strip()
    if not out and result.stderr.strip():
        ui.log("error", f"{tag} · {result.stderr.strip().splitlines()[-1]}", ui.RED)
    return out


def get_clickables():
    """Return clickable controls in the active window as a list of dicts with
    keys ``x, y, w, h, name, role`` (screen coordinates)."""
    # Headroom over the default: pruning keeps the common case well under a
    # second, but a cold AT-SPI bridge plus a large window can need a little more.
    out = _run_script(_CLICKABLES_SCRIPT, tag="labels", timeout=12)
    if not out:
        return []
    try:
        data = json.loads(out)
    except (json.JSONDecodeError, ValueError):
        return []
    return data if isinstance(data, list) else []


def insert_text(text):
    """Type *text* into the focused editable via AT-SPI. Returns True on success."""
    if not text:
        return False
    out = _run_script(_INSERT_SCRIPT, text, tag="dictation")
    return "OK" in out


def read_window_text(limit=4000):
    """Return the visible text of the active window (truncated to *limit*)."""
    out = _run_script(_READ_SCRIPT, tag="read")
    return out[:limit] if out else ""
