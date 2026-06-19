import subprocess

from EchoBase.core import ui

NAME = "window"
DESCRIPTION = "Window and workspace management"

COMMANDS = [
    "minimize - minimize current window",
    "maximize - maximize current window",
    "restore window - unmaximize",
    "fullscreen / exit fullscreen",
    "close window - close current window",
    "snap left / snap right - tile to half",
    "next workspace / previous workspace",
    "workspace [1-9] - jump to workspace number",
]

# Canonical spoken forms for the fuzzy near-miss recovery (main._recover).
PHRASES = [
    "minimize",
    "maximize",
    "restore window",
    "fullscreen",
    "exit fullscreen",
    "close window",
    "snap left",
    "snap right",
    "next workspace",
    "previous workspace",
]

NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "won": 1,
    "to": 2,
    "too": 2,
    "for": 4,
    "ate": 8,
}

core = None


def setup(c):
    global core
    core = c


def dbus_call(method, *args):
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
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        ui.log(
            "error",
            f"window · {result.stderr.strip() or 'extension not enabled'}",
            ui.RED,
        )
        return False
    return True


def parse_workspace_number(text):
    """Return 0-based workspace index, or None if no number found."""
    for word in text.split():
        if word.isdigit():
            n = int(word)
            if 1 <= n <= 9:
                return n - 1
        if word in NUMBER_WORDS:
            return NUMBER_WORDS[word] - 1
    return None


def handle(cmd, core):
    c = cmd.lower().strip()

    if c in ("minimize", "minimize window", "hide window"):
        if dbus_call("MinimizeWindow"):
            core.speak("Minimized.")
        return True

    if c in ("maximize", "maximize window"):
        if dbus_call("MaximizeWindow"):
            core.speak("Maximized.")
        return True

    if c in ("restore window", "unmaximize", "restore"):
        if dbus_call("UnmaximizeWindow"):
            core.speak("Restored.")
        return True

    if c == "fullscreen" or c == "go fullscreen" or c == "make fullscreen":
        if dbus_call("FullscreenWindow"):
            core.speak("Fullscreen.")
        return True

    if c in ("exit fullscreen", "leave fullscreen", "unfullscreen"):
        if dbus_call("UnfullscreenWindow"):
            core.speak("Exited fullscreen.")
        return True

    if c in ("close window", "close this window", "kill window"):
        if dbus_call("CloseWindow"):
            core.speak("Window closed.")
        return True

    if c in ("snap left", "tile left", "window left"):
        if dbus_call("TileLeft"):
            core.speak("Snapped left.")
        return True

    if c in ("snap right", "tile right", "window right"):
        if dbus_call("TileRight"):
            core.speak("Snapped right.")
        return True

    if c in ("next workspace", "workspace next", "workspace right"):
        if dbus_call("NextWorkspace"):
            core.speak("Next workspace.")
        return True

    if c in (
        "previous workspace",
        "workspace previous",
        "workspace left",
        "last workspace",
    ):
        if dbus_call("PrevWorkspace"):
            core.speak("Previous workspace.")
        return True

    # "workspace 3", "go to workspace two"
    if "workspace" in c:
        idx = parse_workspace_number(c)
        if idx is not None:
            if dbus_call("SwitchWorkspace", idx):
                core.speak(f"Workspace {idx + 1}.")
            return True

    return None
