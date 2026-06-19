NAME = "apps"
DESCRIPTION = "Launch and close applications"

COMMANDS = [
    "open/launch [app] - open an application",
    "close [app] - close an application",
    "Apps: firefox, chrome, steam, spotify, files, calculator, settings,",
    "      terminal, browser, vs code, libreoffice, gimp, inkscape, blender,",
    "      vlc, thunderbird, discord, slack, telegram, signal, zoom, obs,",
    "      audacity, system monitor, weather, clocks, maps, contacts, music",
]

# Flatpak apps — keys are user-spoken names, values are flatpak app IDs.
FLATPAK_APPS = {
    "firefox": "org.mozilla.firefox",
    "chrome": "com.google.Chrome",
    "chromium": "org.chromium.Chromium",
    "brave": "com.brave.Browser",
    "steam": "com.valvesoftware.Steam",
    "spotify": "com.spotify.Client",
    "calculator": "org.gnome.Calculator",
    "settings": "org.gnome.Settings",
    "vs code": "com.visualstudio.code",
    "vscode": "com.visualstudio.code",
    "code editor": "com.visualstudio.code",
    "visual studio code": "com.visualstudio.code",
    "libreoffice": "org.libreoffice.LibreOffice",
    "writer": "org.libreoffice.LibreOffice",
    "calc": "org.libreoffice.LibreOffice",
    "impress": "org.libreoffice.LibreOffice",
    "gimp": "org.gimp.GIMP",
    "inkscape": "org.inkscape.Inkscape",
    "blender": "org.blender.Blender",
    "vlc": "org.videolan.VLC",
    "thunderbird": "org.mozilla.Thunderbird",
    "discord": "com.discordapp.Discord",
    "slack": "com.slack.Slack",
    "telegram": "org.telegram.desktop",
    "signal": "org.signal.Signal",
    "zoom": "us.zoom.Zoom",
    "obs": "com.obsproject.Studio",
    "obs studio": "com.obsproject.Studio",
    "audacity": "org.audacityteam.Audacity",
    "kdenlive": "org.kde.kdenlive",
    "weather": "org.gnome.Weather",
    "clocks": "org.gnome.clocks",
    "clock": "org.gnome.clocks",
    "maps": "org.gnome.Maps",
    "contacts": "org.gnome.Contacts",
    "music": "org.gnome.Music",
    "photos": "org.gnome.Photos",
    "image viewer": "org.gnome.Loupe",
    "text editor": "org.gnome.TextEditor",
    "fragments": "de.haeckerfelix.Fragments",
    "bottles": "com.usebottles.bottles",
}

# Local binary apps — keys are user-spoken names, values are binary names
# (or composite commands like "gnome-terminal -- htop").
LOCAL_APPS = {
    "files": "nautilus",
    "file manager": "nautilus",
    "nautilus": "nautilus",
    "dolphin": "dolphin",
    "thunar": "thunar",
    "nemo": "nemo",
    "terminal": "gnome-terminal",
    "console": "gnome-terminal",
    "shell": "gnome-terminal",
    "browser": "qutebrowser",
    "qutebrowser": "qutebrowser",
    "code": "code",
    "system monitor": "gnome-system-monitor",
    "task manager": "gnome-system-monitor",
    "monitor": "gnome-system-monitor",
    "htop": "gnome-terminal -- htop",
    "btop": "gnome-terminal -- btop",
    "neovim": "gnome-terminal -- nvim",
    "vim": "gnome-terminal -- vim",
    "music player": "rhythmbox",
    "rhythmbox": "rhythmbox",
}

core = None

# Canonical "open <app>" phrases for the "did you mean …?" near-miss recovery
# (e.g. a misheard "open fire folks" -> "open firefox"). Built from the app name
# tables so it stays in sync. A representative subset is offered to keep the
# suggestion list focused on the apps people actually launch by voice.
_SUGGEST_APPS = [
    "firefox", "chrome", "chromium", "brave", "spotify", "steam",
    "calculator", "settings", "vs code", "libreoffice", "gimp", "vlc",
    "thunderbird", "discord", "slack", "telegram", "signal", "zoom",
    "obs", "audacity", "weather", "clocks", "maps", "contacts", "music",
    "files", "terminal", "browser", "system monitor",
]
PHRASES = [f"open {a}" for a in _SUGGEST_APPS] + [
    f"close {a}" for a in _SUGGEST_APPS
]


def setup(c):
    global core
    core = c


def find_app(name, core):
    """Find app - returns (type, id)"""
    if name in FLATPAK_APPS:
        result = core.host_run(["flatpak", "info", FLATPAK_APPS[name]])
        if result.returncode == 0:
            return ("flatpak", FLATPAK_APPS[name])

    if name in LOCAL_APPS:
        return ("local", LOCAL_APPS[name])

    result = core.host_run(["which", name])
    if result.returncode == 0:
        return ("local", name)

    return (None, None)


def launch_app(name, core):
    app_type, app_id = find_app(name, core)
    if app_type == "flatpak":
        core.host_run(["flatpak", "run", app_id], background=True)
        return True
    elif app_type == "local":
        # Composite commands like "gnome-terminal -- htop" need splitting.
        cmd = app_id.split() if " " in app_id else [app_id]
        core.host_run(cmd, background=True)
        return True
    return False


def close_app(name, core):
    app_type, app_id = find_app(name, core)
    if app_type == "flatpak":
        core.host_run(["flatpak", "kill", app_id])
        return True
    elif app_type == "local":
        # For composite commands, kill the underlying tool not the wrapper.
        binary = app_id.split()[-1] if " " in app_id else app_id
        core.host_run(["pkill", "-f", binary])
        return True
    return False


def handle(cmd, core):
    all_apps = sorted(
        set(FLATPAK_APPS.keys()) | set(LOCAL_APPS.keys()),
        key=len,
        reverse=True,
    )

    for app in all_apps:
        if ("open" in cmd or "launch" in cmd or "start" in cmd) and app in cmd:
            if launch_app(app, core):
                core.speak(f"Opening {app}.")
            else:
                core.speak(f"{app} not installed.")
            return True

        if ("close" in cmd or "quit" in cmd or "kill" in cmd) and app in cmd:
            close_app(app, core)
            core.speak(f"Closing {app}.")
            return True

    return None
