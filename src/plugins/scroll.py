"""Global scrolling — works anywhere, including while head tracking is active.

The other scroll affordances are mode-bound (qutebrowser's JS scroll, the grid's
in-mode scroll). This plugin adds plain mouse-wheel scrolling at the pointer that
the main dispatcher can run at any time, so "scroll down" works on its own and,
crucially, *while head tracking is running* (it scrolls at the live tracked
cursor). It also offers hands-free continuous scrolling: "keep scrolling down"
auto-scrolls until you say "stop", so a no-hands user needn't repeat the command.
"""

import re
import threading

from EchoBase.core import ui

NAME = "scroll"
DESCRIPTION = "Scroll the window at the pointer, including hands-free auto-scroll"

COMMANDS = [
    "scroll up / scroll down / scroll left / scroll right - scroll at the pointer",
    "scroll down five - scroll a set amount",
    "keep scrolling down - auto-scroll until you say stop",
]

PHRASES = [
    "scroll up",
    "scroll down",
    "scroll left",
    "scroll right",
    "keep scrolling",
    "keep scrolling down",
    "keep scrolling up",
    "stop scrolling",
]

core = None

_CONTINUOUS = (
    "keep scrolling",
    "auto scroll",
    "autoscroll",
    "automatic scroll",
    "continuous scroll",
    "scroll continuously",
    "keep going",
)

_STOP_WORDS = {
    "stop",
    "enough",
    "cancel",
    "done",
    "halt",
    "exit",
    "quit",
    "okay",
    "stop scrolling",
    "that's enough",
}

_NUM_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


def setup(c):
    global core
    core = c


def _dbus(method, *args):
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
    return core.host_run(cmd)


def _screen_size():
    """Primary screen size from the extension, or a sane default."""
    result = _dbus("GetScreenSize")
    if getattr(result, "returncode", 1) == 0:
        m = re.search(r"\((\d+),\s*(\d+)\)", result.stdout or "")
        if m:
            return int(m.group(1)), int(m.group(2))
    return 1920, 1080


def _point():
    """Where to scroll: the live tracked cursor if head tracking is running,
    otherwise the centre of the screen (scrolls the focused window)."""
    pos = getattr(core, "_tracking_pos", None)
    if pos:
        return pos
    w, h = _screen_size()
    return w // 2, h // 2


def _direction(cmd):
    if "up" in cmd:
        return "up"
    if "left" in cmd:
        return "left"
    if "right" in cmd:
        return "right"
    return "down"  # default


def _amount(cmd):
    m = re.search(r"\b(\d{1,2})\b", cmd)
    if m:
        return max(1, min(20, int(m.group(1))))
    for word, n in _NUM_WORDS.items():
        if re.search(rf"\b{word}\b", cmd):
            return n
    return 3


def _scroll(direction, clicks):
    x, y = _point()
    _dbus("Scroll", x, y, direction, clicks)


def continuous_scroll(direction):
    """Auto-scroll in *direction* until the user says a stop word."""
    stop = threading.Event()

    def worker():
        while not stop.is_set():
            _scroll(direction, 2)
            stop.wait(0.25)

    worker_thread = threading.Thread(target=worker, daemon=True)
    worker_thread.start()
    core.speak(f"Scrolling {direction}. Say stop when you're there.")
    ui.log("scroll", f"continuous {direction}", ui.CYAN)
    try:
        while True:
            core.flush_stream()
            first = core.wait_for_speech(timeout=20)
            if not first:
                continue
            audio = first + core.record_until_silence()
            said = (
                (core.transcribe(audio, prompt="stop enough cancel") or "")
                .lower()
                .strip(".,!? ")
            )
            if not said:
                continue
            if said in _STOP_WORDS or any(w in said.split() for w in _STOP_WORDS):
                break
    finally:
        stop.set()
    core.speak("Stopped.")
    return True


def handle(cmd, core):
    c = cmd.lower().strip(".,!? ")

    if "scroll" not in c and not any(t in c for t in _CONTINUOUS):
        return None

    # Explicit "stop scrolling" outside a continuous loop is a harmless no-op.
    if c in ("stop scrolling", "stop scroll"):
        return True

    if any(t in c for t in _CONTINUOUS):
        return continuous_scroll(_direction(c))

    _scroll(_direction(c), _amount(c))
    return True
