import datetime
import os
import re
import subprocess

NAME = "system"
DESCRIPTION = "System controls"

COMMANDS = [
    "volume up/down - adjust volume",
    "volume max / volume min / volume [0-100] - set volume",
    "mute / unmute - toggle speaker mute",
    "mute mic / unmute mic - toggle microphone mute",
    "brightness up/down - adjust screen brightness",
    "do not disturb on/off - toggle notifications",
    "lock / lock screen - lock the screen",
    "suspend / sleep - suspend the system",
    "screenshot - capture full screen",
    "screenshot area - capture a region",
]

# Canonical spoken forms for the fuzzy near-miss recovery (main._recover).
PHRASES = [
    "lock screen",
    "suspend",
    "screenshot",
    "screenshot area",
    "volume up",
    "volume down",
    "mute",
    "unmute",
    "mute microphone",
    "brightness up",
    "brightness down",
    "do not disturb on",
    "do not disturb off",
]

core = None


def setup(c):
    global core
    core = c


# --- Volume ---


def volume_up(core):
    core.host_run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "10%+"])


def volume_down(core):
    core.host_run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "10%-"])


def volume_set(core, percent):
    """Set volume to an absolute percentage (0-100)."""
    pct = max(0, min(100, int(percent)))
    core.host_run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{pct / 100:.2f}"])


def volume_mute(core):
    core.host_run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"])


def mic_mute(core):
    core.host_run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SOURCE@", "toggle"])


# --- Brightness ---


def brightness_up(core):
    core.host_run(
        [
            "gdbus",
            "call",
            "--session",
            "--dest",
            "org.gnome.SettingsDaemon.Power",
            "--object-path",
            "/org/gnome/SettingsDaemon/Power",
            "--method",
            "org.gnome.SettingsDaemon.Power.Screen.StepUp",
        ]
    )


def brightness_down(core):
    core.host_run(
        [
            "gdbus",
            "call",
            "--session",
            "--dest",
            "org.gnome.SettingsDaemon.Power",
            "--object-path",
            "/org/gnome/SettingsDaemon/Power",
            "--method",
            "org.gnome.SettingsDaemon.Power.Screen.StepDown",
        ]
    )


# --- DND ---


def dnd_on(core):
    core.host_run(
        ["gsettings", "set", "org.gnome.desktop.notifications", "show-banners", "false"]
    )


def dnd_off(core):
    core.host_run(
        ["gsettings", "set", "org.gnome.desktop.notifications", "show-banners", "true"]
    )


# --- Power ---


def lock_screen(core):
    core.host_run(["loginctl", "lock-session"])


def suspend(core):
    core.host_run(["systemctl", "suspend"])


# --- Screenshots ---


def _screenshot_path():
    pictures = os.path.expanduser("~/Pictures/Screenshots")
    os.makedirs(pictures, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    return os.path.join(pictures, f"screenshot-{stamp}.png")


def _has(binary):
    return subprocess.run(["which", binary], capture_output=True).returncode == 0


def _shell_screenshot(core, path):
    """Use the built-in GNOME Shell D-Bus Screenshot service. Works on Wayland
    without any extra packages. Returns True on success."""
    result = core.host_run(
        [
            "gdbus",
            "call",
            "--session",
            "--dest",
            "org.gnome.Shell.Screenshot",
            "--object-path",
            "/org/gnome/Shell/Screenshot",
            "--method",
            "org.gnome.Shell.Screenshot.Screenshot",
            "true",  # include cursor
            "false",  # flash
            path,
        ]
    )
    return result.returncode == 0 and "true" in result.stdout


def _shell_screenshot_interactive(core):
    """Open the GNOME Shell native screenshot UI (lets user pick area/window/screen)."""
    result = core.host_run(
        [
            "gdbus",
            "call",
            "--session",
            "--dest",
            "org.gnome.Shell.Screenshot",
            "--object-path",
            "/org/gnome/Shell/Screenshot",
            "--method",
            "org.gnome.Shell.Screenshot.InteractiveScreenshot",
        ]
    )
    return result.returncode == 0


def screenshot_full(core):
    path = _screenshot_path()
    if _has("gnome-screenshot"):
        core.host_run(["gnome-screenshot", "-f", path])
        return path
    if _has("grim"):
        core.host_run(["grim", path])
        return path
    if _shell_screenshot(core, path):
        return path
    return None


def screenshot_area(core):
    if _has("gnome-screenshot"):
        core.host_run(["gnome-screenshot", "-a"], background=True)
        return True
    if _has("grim") and _has("slurp"):
        core.host_run(
            ["sh", "-c", f'grim -g "$(slurp)" {_screenshot_path()}'],
            background=True,
        )
        return True
    # Fallback: GNOME Shell native screenshot UI
    return _shell_screenshot_interactive(core)


# --- Handler ---


def _extract_percent(cmd):
    """Extract a 0-100 number from a command, or None."""
    match = re.search(r"\b(\d{1,3})\b", cmd)
    if not match:
        return None
    n = int(match.group(1))
    return n if 0 <= n <= 100 else None


def handle(cmd, core):
    # --- Power: lock & suspend ---
    if cmd in ("lock", "lock screen", "lock the screen", "lock my screen"):
        lock_screen(core)
        core.speak("Locking.")
        return True

    if cmd in ("suspend", "sleep", "go to sleep", "suspend the system"):
        core.speak("Suspending.")
        suspend(core)
        return True

    # --- Screenshots ---
    if "screenshot" in cmd or cmd in ("take a picture", "snapshot", "capture screen"):
        if "area" in cmd or "region" in cmd or "select" in cmd:
            if screenshot_area(core):
                core.speak("Select an area.")
            else:
                core.speak("Install gnome-screenshot or grim to use screenshots.")
            return True
        path = screenshot_full(core)
        if path:
            core.speak("Screenshot saved.")
        else:
            core.speak("Install gnome-screenshot or grim to use screenshots.")
        return True

    # --- Microphone ---
    if ("mic" in cmd or "microphone" in cmd) and ("mute" in cmd or "unmute" in cmd):
        mic_mute(core)
        core.speak("Microphone toggled.")
        return True

    # --- Volume ---
    if "volume" in cmd or "sound" in cmd:
        if "max" in cmd or "maximum" in cmd or "full" in cmd:
            volume_set(core, 100)
            core.speak("Volume max.")
            return True
        if "min" in cmd or "minimum" in cmd or "zero" in cmd:
            volume_set(core, 0)
            core.speak("Volume zero.")
            return True
        pct = _extract_percent(cmd)
        if pct is not None:
            volume_set(core, pct)
            core.speak(f"Volume {pct}.")
            return True
        if "up" in cmd or "louder" in cmd:
            volume_up(core)
            core.speak("Volume up.")
            return True
        elif "down" in cmd or "quieter" in cmd or "softer" in cmd:
            volume_down(core)
            core.speak("Volume down.")
            return True
        elif "mute" in cmd or "unmute" in cmd:
            volume_mute(core)
            core.speak("Toggled mute.")
            return True

    if "mute" in cmd:
        volume_mute(core)
        core.speak("Toggled mute.")
        return True

    # --- Brightness ---
    if "brightness" in cmd or "screen" in cmd:
        if "up" in cmd or "brighter" in cmd:
            brightness_up(core)
            core.speak("Brighter.")
            return True
        elif "down" in cmd or "dimmer" in cmd or "darker" in cmd:
            brightness_down(core)
            core.speak("Dimmer.")
            return True

    # --- Do Not Disturb ---
    if "do not disturb" in cmd or "dnd" in cmd or "notifications" in cmd:
        if "on" in cmd or "enable" in cmd:
            dnd_on(core)
            core.speak("Do not disturb on.")
            return True
        elif "off" in cmd or "disable" in cmd:
            dnd_off(core)
            core.speak("Do not disturb off.")
            return True

    return None
