import subprocess

from EchoBase.core import atspi

NAME = "a11y"
DESCRIPTION = "Accessibility toggles and read-aloud"

COMMANDS = [
    "magnify / magnifier on/off - toggle screen magnifier",
    "zoom in / zoom out - step magnifier zoom level",
    "high contrast on/off - toggle high contrast theme",
    "large text on/off - toggle text scaling 1.5x",
    "big cursor on/off - toggle large cursor (48px)",
    "screen reader on/off - toggle Orca",
    "on-screen keyboard on/off - toggle GNOME OSK",
    "night light on/off - toggle blue light filter",
    "sticky keys on/off - toggle sticky keys",
    "slow keys on/off - toggle slow keys",
    "bounce keys on/off - ignore rapid repeated keypresses",
    "mouse keys on/off - move the pointer with the numpad",
    "dwell click on/off - click by hovering (GNOME hover click)",
    "key repeat on/off - toggle held-key auto-repeat",
    "pointer faster / slower - adjust mouse pointer speed",
    "double click slower / faster - adjust double-click delay",
    "read selection / read this - speak highlighted text",
    "read the page / read screen - speak the active window's text",
]

# gsettings (schema, key, default-on, default-off) for boolean toggles
TOGGLES = {
    "magnifier": (
        "org.gnome.desktop.a11y.applications",
        "screen-magnifier-enabled",
        "true",
        "false",
    ),
    "high contrast": (
        "org.gnome.desktop.a11y.interface",
        "high-contrast",
        "true",
        "false",
    ),
    "screen reader": (
        "org.gnome.desktop.a11y.applications",
        "screen-reader-enabled",
        "true",
        "false",
    ),
    "screen keyboard": (
        "org.gnome.desktop.a11y.applications",
        "screen-keyboard-enabled",
        "true",
        "false",
    ),
    "night light": (
        "org.gnome.settings-daemon.plugins.color",
        "night-light-enabled",
        "true",
        "false",
    ),
    "sticky keys": (
        "org.gnome.desktop.a11y.keyboard",
        "stickykeys-enable",
        "true",
        "false",
    ),
    "slow keys": (
        "org.gnome.desktop.a11y.keyboard",
        "slowkeys-enable",
        "true",
        "false",
    ),
    "bounce keys": (
        "org.gnome.desktop.a11y.keyboard",
        "bouncekeys-enable",
        "true",
        "false",
    ),
    "mouse keys": (
        "org.gnome.desktop.a11y.keyboard",
        "mousekeys-enable",
        "true",
        "false",
    ),
    "dwell click": (
        "org.gnome.desktop.a11y.mouse",
        "dwell-click-enabled",
        "true",
        "false",
    ),
    "key repeat": ("org.gnome.desktop.peripherals.keyboard", "repeat", "true", "false"),
}

LARGE_TEXT_SCHEMA = ("org.gnome.desktop.interface", "text-scaling-factor")
CURSOR_SIZE_SCHEMA = ("org.gnome.desktop.interface", "cursor-size")
MAG_FACTOR_SCHEMA = ("org.gnome.desktop.a11y.magnifier", "mag-factor")
POINTER_SPEED_SCHEMA = ("org.gnome.desktop.peripherals.mouse", "speed")
DOUBLE_CLICK_SCHEMA = ("org.gnome.desktop.peripherals.mouse", "double-click")

LARGE_TEXT_ON, LARGE_TEXT_OFF = "1.5", "1.0"
CURSOR_LARGE, CURSOR_NORMAL = "48", "24"
ZOOM_STEP, ZOOM_MIN, ZOOM_MAX = 0.5, 1.0, 8.0
POINTER_STEP, POINTER_MIN, POINTER_MAX = 0.2, -1.0, 1.0
DCLICK_STEP, DCLICK_MIN, DCLICK_MAX = 100, 100, 2000

core = None


def setup(c):
    global core
    core = c


def gset(schema, key, value):
    core.host_run(["gsettings", "set", schema, key, value])


def gget(schema, key):
    """Return current gsettings value as a string ('true'/'false'/'1.5'/etc.) or None on failure."""
    result = core.host_run(["gsettings", "get", schema, key])
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def toggle_bool(schema, key):
    """Flip a boolean gsetting; returns the new value as a bool."""
    current = gget(schema, key)
    new_val = "false" if current == "true" else "true"
    gset(schema, key, new_val)
    return new_val == "true"


def step_zoom(direction):
    """Step the magnifier zoom level. direction is +1 or -1."""
    current = gget(*MAG_FACTOR_SCHEMA)
    try:
        cur = float(current) if current else 2.0
    except ValueError:
        cur = 2.0
    new = max(ZOOM_MIN, min(ZOOM_MAX, cur + direction * ZOOM_STEP))
    gset(MAG_FACTOR_SCHEMA[0], MAG_FACTOR_SCHEMA[1], f"{new:.1f}")
    # Make sure the magnifier is on when zooming.
    gset("org.gnome.desktop.a11y.applications", "screen-magnifier-enabled", "true")
    return new


def step_pointer_speed(direction):
    """Step the mouse pointer speed (gsettings range -1.0..1.0). +1 faster."""
    current = gget(*POINTER_SPEED_SCHEMA)
    try:
        cur = float(current) if current is not None else 0.0
    except ValueError:
        cur = 0.0
    new = max(POINTER_MIN, min(POINTER_MAX, cur + direction * POINTER_STEP))
    gset(POINTER_SPEED_SCHEMA[0], POINTER_SPEED_SCHEMA[1], f"{new:.2f}")
    return new


def step_double_click(direction):
    """Step the double-click interval in milliseconds. +1 = longer/easier."""
    current = gget(*DOUBLE_CLICK_SCHEMA)
    try:
        cur = int(current) if current is not None else 400
    except ValueError:
        cur = 400
    new = max(DCLICK_MIN, min(DCLICK_MAX, cur + direction * DCLICK_STEP))
    gset(DOUBLE_CLICK_SCHEMA[0], DOUBLE_CLICK_SCHEMA[1], str(new))
    return new


def read_selection(core):
    """Read the primary X11 / Wayland selection aloud via piper."""
    if subprocess.run(["which", "wl-paste"], capture_output=True).returncode != 0:
        core.speak("wl-clipboard is not installed.")
        return
    result = core.host_run(["wl-paste", "--primary", "--no-newline"])
    text = (result.stdout or "").strip()
    if not text:
        core.speak("Nothing selected.")
        return
    # Cap to a reasonable length so a giant selection doesn't run forever.
    if len(text) > 800:
        text = text[:800] + "."
    core.speak(text)


def read_screen(core):
    """Read the active window's visible text aloud via AT-SPI."""
    text = atspi.read_window_text()
    if not text:
        core.speak("I couldn't read any text from this window.")
        return
    if len(text) > 1500:
        text = text[:1500] + ". And there's more."
    core.speak(text)


# --- Handler ---


def _on_off(cmd):
    """Return True if 'on'/'enable', False if 'off'/'disable', None if not present."""
    if "on" in cmd.split() or "enable" in cmd or "turn on" in cmd:
        return True
    if "off" in cmd.split() or "disable" in cmd or "turn off" in cmd:
        return False
    return None


def handle(cmd, core):
    c = cmd.lower().strip()

    # Read the whole active window aloud
    if c in (
        "read the page",
        "read page",
        "read screen",
        "read the screen",
        "read window",
        "read the window",
        "read everything",
        "read all",
    ):
        read_screen(core)
        return True

    # Read selection aloud
    if c in (
        "read selection",
        "read this",
        "read aloud",
        "speak selection",
        "say this",
    ):
        read_selection(core)
        return True

    # Zoom in/out (always implies magnifier on)
    if c in ("zoom in", "zoom closer", "magnify in"):
        new = step_zoom(+1)
        core.speak(f"Zoom {new:.1f}.")
        return True

    if c in ("zoom out", "zoom further", "magnify out"):
        new = step_zoom(-1)
        core.speak(f"Zoom {new:.1f}.")
        return True

    # Large text
    if "large text" in c or "big text" in c:
        target = _on_off(c)
        if target is None:
            current = gget(*LARGE_TEXT_SCHEMA)
            target = current == LARGE_TEXT_OFF
        gset(
            LARGE_TEXT_SCHEMA[0],
            LARGE_TEXT_SCHEMA[1],
            LARGE_TEXT_ON if target else LARGE_TEXT_OFF,
        )
        core.speak(f"Large text {'on' if target else 'off'}.")
        return True

    # Big cursor
    if "big cursor" in c or "large cursor" in c or "huge cursor" in c:
        target = _on_off(c)
        if target is None:
            current = gget(*CURSOR_SIZE_SCHEMA)
            target = current == CURSOR_NORMAL
        gset(
            CURSOR_SIZE_SCHEMA[0],
            CURSOR_SIZE_SCHEMA[1],
            CURSOR_LARGE if target else CURSOR_NORMAL,
        )
        core.speak(f"Big cursor {'on' if target else 'off'}.")
        return True

    # Pointer speed: "pointer faster/slower", "mouse speed up/down"
    if ("pointer" in c or "mouse" in c or "cursor" in c) and (
        "fast" in c or "slow" in c or "speed" in c or "quick" in c
    ):
        faster = "fast" in c or "quick" in c or "up" in c or "increase" in c
        if faster or "slow" in c or "down" in c or "decrease" in c:
            new = step_pointer_speed(+1 if faster else -1)
            core.speak("Pointer faster." if faster else "Pointer slower.")
            return True

    # Double-click delay: "double click slower/faster/longer/shorter"
    if "double" in c and ("click" in c or "tap" in c):
        if any(w in c for w in ("slow", "long", "more time", "easier")):
            step_double_click(+1)
            core.speak("Double-click delay increased.")
            return True
        if any(w in c for w in ("fast", "short", "less time", "quick")):
            step_double_click(-1)
            core.speak("Double-click delay decreased.")
            return True

    # Boolean toggles (loop in length-desc order so "screen keyboard" beats "screen")
    aliases = {
        "magnifier": ["magnifier", "magnify", "screen magnifier"],
        "high contrast": ["high contrast", "contrast"],
        "screen reader": ["screen reader", "orca"],
        "screen keyboard": [
            "screen keyboard",
            "on-screen keyboard",
            "on screen keyboard",
            "osk",
            "virtual keyboard",
        ],
        "night light": ["night light", "blue light", "warm screen"],
        "sticky keys": ["sticky keys"],
        "slow keys": ["slow keys"],
        "bounce keys": ["bounce keys", "bouncy keys"],
        "mouse keys": ["mouse keys", "mousekeys", "numpad mouse", "keyboard mouse"],
        "dwell click": [
            "dwell click",
            "hover click",
            "dwell clicking",
            "hover clicking",
        ],
        "key repeat": ["key repeat", "repeat keys", "keyboard repeat", "auto repeat"],
    }

    matches = []
    for setting, names in aliases.items():
        for name in names:
            if name in c:
                matches.append((len(name), setting))
                break
    if matches:
        matches.sort(reverse=True)
        setting = matches[0][1]
        schema, key, on_val, off_val = TOGGLES[setting]
        target = _on_off(c)
        if target is None:
            new_state = toggle_bool(schema, key)
        else:
            gset(schema, key, on_val if target else off_val)
            new_state = target
        core.speak(f"{setting} {'on' if new_state else 'off'}.")
        return True

    return None
