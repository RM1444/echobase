import re

from EchoBase.core import ui

NAME = "keyboard"
DESCRIPTION = "Press keys and keyboard shortcuts by voice"

COMMANDS = [
    "press enter / tab / escape / space / backspace / delete",
    "press up / down / left / right - arrow keys",
    "page up / page down / home / end",
    "press [letter] / press control c - any key or combo",
    "copy / paste / cut - clipboard shortcuts",
    "undo / redo / select all / save / print",
    "switch app / alt tab - switch applications",
]

# Canonical spoken forms for the fuzzy near-miss recovery (main._recover).
PHRASES = [
    "copy",
    "paste",
    "cut",
    "undo",
    "redo",
    "select all",
    "save",
    "print",
    "switch app",
    "press enter",
    "press tab",
    "press escape",
    "press space",
    "press backspace",
    "press delete",
]

core = None

# Names the GNOME extension's PressKey understands (after stripping spaces).
_NAMED_KEYS = {
    "enter": "enter",
    "return": "enter",
    "new line": "enter",
    "tab": "tab",
    "back tab": "backtab",
    "backtab": "backtab",
    "escape": "escape",
    "esc": "escape",
    "space": "space",
    "spacebar": "space",
    "space bar": "space",
    "backspace": "backspace",
    "back space": "backspace",
    "delete": "delete",
    "forward delete": "delete",
    "up": "up",
    "arrow up": "up",
    "down": "down",
    "arrow down": "down",
    "left": "left",
    "arrow left": "left",
    "right": "right",
    "arrow right": "right",
    "home": "home",
    "end": "end",
    "page up": "pageup",
    "pageup": "pageup",
    "page down": "pagedown",
    "pagedown": "pagedown",
    "menu": "menu",
    "context menu": "menu",
    "refresh": "f5",
    "full screen": "f11",
    "fullscreen": "f11",
}

# Whole-phrase shortcuts -> key combo strings the extension parses.
_SHORTCUTS = {
    "copy": "ctrl+c",
    "paste": "ctrl+v",
    "cut": "ctrl+x",
    "undo": "ctrl+z",
    "redo": "ctrl+y",
    "select all": "ctrl+a",
    "save": "ctrl+s",
    "save as": "ctrl+shift+s",
    "print": "ctrl+p",
    "switch app": "alt+tab",
    "switch application": "alt+tab",
    "switch apps": "alt+tab",
    "alt tab": "alt+tab",
    "next application": "alt+tab",
}

# Bare key names safe to accept without a "press" prefix (unambiguous).
_BARE_KEYS = {
    "enter",
    "return",
    "escape",
    "tab",
    "backspace",
    "delete",
    "page up",
    "page down",
    "home",
    "end",
}

# Spoken modifier words -> canonical tokens for combo building.
_MOD_ALIASES = {
    "control": "ctrl",
    "ctrl": "ctrl",
    "command": "super",
    "cmd": "super",
    "windows": "super",
    "super": "super",
    "meta": "super",
    "shift": "shift",
    "alt": "alt",
    "option": "alt",
    "plus": "+",
}

_PREFIXES = (
    "press the ",
    "press ",
    "hit the ",
    "hit ",
    "tap the ",
    "tap ",
    "key ",
    "type key ",
)


def setup(c):
    global core
    core = c


def _dbus(method, arg):
    """Call a keyboard method on the GNOME Shell extension. Returns True on ok."""
    result = core.host_run(
        [
            "gdbus",
            "call",
            "--session",
            "--dest",
            "org.gnome.Shell",
            "--object-path",
            "/org/EchoBase/Grid",
            "--method",
            f"org.EchoBase.Grid.{method}",
            arg,
        ]
    )
    if result.returncode != 0:
        ui.log(
            "error",
            f"keyboard · {result.stderr.strip() or 'extension not enabled'}",
            ui.RED,
        )
        return False
    return "true" in (result.stdout or "").lower()


def _press_named(name):
    """Press a single named key. Returns True if it was a known key."""
    key = _NAMED_KEYS.get(name)
    if not key:
        return False
    if _dbus("PressKey", key):
        core.speak(f"{name}.")
    return True


def _build_combo(text):
    """Turn 'control c' / 'ctrl + shift + t' into 'ctrl+shift+t', or None."""
    tokens = [t for t in re.split(r"[\s+]+", text) if t]
    tokens = [_MOD_ALIASES.get(t, t) for t in tokens if t != "+"]
    if len(tokens) < 2:
        return None
    *mods, key = tokens
    if not all(m in ("ctrl", "shift", "alt", "super") for m in mods):
        return None
    # Key must be a single char or a known named key.
    if len(key) != 1 and key not in _NAMED_KEYS:
        return None
    key = _NAMED_KEYS.get(key, key)
    return "+".join(mods + [key])


def _press_freeform(text):
    """Handle 'press X' where X is a key name, single char, or a combo."""
    text = text.strip(".,!? ")
    if text in _NAMED_KEYS:
        return _press_named(text)
    combo = _build_combo(text)
    if combo:
        if _dbus("KeyCombo", combo):
            core.speak(f"{text}.")
        return True
    if len(text) == 1 and text.isalnum():
        if _dbus("KeyCombo", text):
            core.speak(f"{text}.")
        return True
    return False


def handle(cmd, core):
    c = cmd.lower().strip(".,!? ")

    # Whole-phrase shortcuts (copy/paste/save/alt-tab/...).
    if c in _SHORTCUTS:
        if _dbus("KeyCombo", _SHORTCUTS[c]):
            core.speak(f"{c}.")
        return True

    # Explicit "press / hit / tap <something>".
    for prefix in _PREFIXES:
        if c.startswith(prefix):
            rest = c[len(prefix) :].strip()
            if _press_freeform(rest):
                return True
            core.speak(f"I don't know the key {rest}.")
            return True

    # Bare unambiguous key names.
    if c in _BARE_KEYS:
        return _press_named(c)

    return None
