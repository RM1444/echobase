import difflib
import json
import re
import time

from EchoBase.core import atspi, ui

NAME = "labels"
DESCRIPTION = "Numbered click-hints over native UI elements (accessibility tree)"

COMMANDS = [
    "show labels / label elements - number clickable controls",
    "buttons / show buttons - same, then say a number to click",
    "click [name] - click a control by its name (e.g. 'click submit')",
    "[number] - click the labelled element",
    "cancel - hide labels",
]

PHRASES = [
    "show labels",
    "show buttons",
    "label buttons",
    "click",
]

core = None

_TRIGGERS = {
    "show labels",
    "label elements",
    "labels",
    "show hints",
    "click labels",
    "show buttons",
    "buttons",
    "label buttons",
    "number the buttons",
    "show controls",
    "label controls",
}

_CANCEL = {
    "cancel",
    "close",
    "never mind",
    "nevermind",
    "exit",
    "stop",
    "escape",
    "hide",
}

_NUMBER_WORDS = {
    "zero": 0,
    "oh": 0,
    "one": 1,
    "won": 1,
    "two": 2,
    "to": 2,
    "too": 2,
    "three": 3,
    "tree": 3,
    "four": 4,
    "for": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "ate": 8,
    "nine": 9,
}

MAX_HINTS = atspi.MAX_HINTS


def setup(c):
    global core
    core = c


def _ext(method, *args, parse="bool"):
    cmd = [
        "gdbus",
        "call",
        "--session",
        "--dest",
        "org.gnome.Shell",
        "--object-path",
        "/org/EchoBase/Grid",
        "--method",
        f"org.EchoBase.Grid.{method}",
    ]
    cmd.extend(str(a) for a in args)
    result = core.host_run(cmd)
    if result.returncode != 0:
        ui.log(
            "error",
            f"labels · {result.stderr.strip() or 'extension not enabled'}",
            ui.RED,
        )
        return None
    return result.stdout


def get_clickables():
    """Clickable controls in the active window (delegates to the shared helper)."""
    return atspi.get_clickables()


def click_element(el):
    """Click an element dict (from get_clickables) at its centre via the
    extension. Returns the element's spoken label."""
    cx = el["x"] + el["w"] // 2
    cy = el["y"] + el["h"] // 2
    _ext("Click", cx, cy, parse="raw")
    return el.get("name") or ""


def click_by_name(core, name):
    """Click the control whose name best matches *name*. Returns True if a
    control was clicked, False if none matched."""
    name = (name or "").strip().lower()
    if not name:
        return False
    elements = [el for el in get_clickables() if el.get("name")]
    if not elements:
        return False

    names = [el["name"].lower() for el in elements]
    # Prefer an exact / substring hit, then fall back to fuzzy matching.
    best = None
    for el, low in zip(elements, names):
        if low == name:
            best = el
            break
        if name in low or low in name:
            best = best or el
    if best is None:
        close = difflib.get_close_matches(name, names, n=1, cutoff=0.6)
        if close:
            best = elements[names.index(close[0])]
    if best is None:
        return False

    label = click_element(best)
    core.speak(f"Clicked {label}." if label else "Clicked.")
    return True


def parse_number(text):
    """Return an integer the user spoke (supports 1-2 digit chains), or None."""
    digits = []
    for word in re.sub(r"[.,!?\-]", " ", text.lower()).split():
        if word.isdigit():
            digits.append(word)
        elif word in _NUMBER_WORDS:
            digits.append(str(_NUMBER_WORDS[word]))
    if not digits:
        return None
    return int("".join(digits))


def _show(core):
    elements = get_clickables()
    if not elements:
        core.speak("I couldn't find any labelled controls in this window.")
        return True

    elements = elements[:MAX_HINTS]
    # Badge at each element's top-left; we click its center.
    hints = [{"n": i + 1, "x": el["x"], "y": el["y"]} for i, el in enumerate(elements)]
    _ext("ShowHints", json.dumps(hints), parse="raw")
    ui.log("labels", f"{len(elements)} clickable elements", ui.CYAN)
    core.speak("Say the number to click.")

    try:
        for _ in range(3):
            core.flush_stream()
            time.sleep(0.1)
            first = core.wait_for_speech(timeout=8)
            audio = first + core.record_until_silence()
            said = core.transcribe(
                audio,
                prompt="one two three four five six seven eight nine cancel",
            )
            said = (said or "").lower().strip(".,!? ")
            if not said:
                continue
            ui.log("heard", said, ui.YELLOW)

            if any(w in said for w in _CANCEL):
                core.speak("Cancelled.")
                return True

            num = parse_number(said)
            if num and 1 <= num <= len(elements):
                el = elements[num - 1]
                _ext("HideHints", parse="raw")
                label = click_element(el)
                core.speak(f"Clicked {label}." if label else "Clicked.")
                return True
            core.speak("Say a number from the labels, or cancel.")
        core.speak("Okay, hiding the labels.")
        return True
    finally:
        _ext("HideHints", parse="raw")


def show(core_ref):
    """Public entry to the numbered-hint flow, reusable by other plugins (e.g.
    browser link clicking). Adopts *core_ref* as this module's core first, so it
    works even when imported under a different package path than the loader used."""
    global core
    core = core_ref
    return _show(core_ref)


def handle(cmd, core):
    c = cmd.lower().strip(".,!? ")
    if c in _TRIGGERS:
        return _show(core)

    # Click a control by name: "click submit", "click the menu button".
    if c.startswith("click "):
        target = c[len("click ") :].strip()
        if target and not target.isdigit():
            for lead in ("the ", "on ", "on the "):
                if target.startswith(lead):
                    target = target[len(lead) :].strip()
            if click_by_name(core, target):
                return True
            core.speak(f"I couldn't find {target} in this window.")
            return True

    return None
