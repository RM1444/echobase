NAME = "media"
DESCRIPTION = "Media playback controls"

COMMANDS = [
    "play - resume playback",
    "pause - pause playback",
    "play pause - toggle play/pause",
    "stop playback / stop music - stop the player",
    "next/skip - next track",
    "previous/back - previous track",
]

# Canonical spoken forms for the fuzzy near-miss recovery (main._recover).
PHRASES = ["play", "pause", "play pause", "stop music", "next track", "previous track"]

core = None


def setup(c):
    global core
    core = c


def get_media_players(core):
    result = core.host_run(
        [
            "dbus-send",
            "--session",
            "--dest=org.freedesktop.DBus",
            "--type=method_call",
            "--print-reply",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus.ListNames",
        ]
    )
    return [
        line.split('"')[1]
        for line in result.stdout.split("\n")
        if "org.mpris.MediaPlayer2." in line
    ]


def media_control(action, core):
    players = get_media_players(core)
    if not players:
        return False

    method = {
        "play": "Play",
        "pause": "Pause",
        "next": "Next",
        "previous": "Previous",
        "stop": "Stop",
        "playpause": "PlayPause",
    }.get(action)

    if not method:
        return False

    for player in players:
        core.host_run(
            [
                "dbus-send",
                "--session",
                "--type=method_call",
                f"--dest={player}",
                "/org/mpris/MediaPlayer2",
                f"org.mpris.MediaPlayer2.Player.{method}",
            ]
        )
    return True


def handle(cmd, core):
    # --- Stop playback (must come before generic 'stop' could be misread elsewhere) ---
    if cmd in (
        "stop playback",
        "stop music",
        "stop the music",
        "stop player",
        "stop track",
        "stop song",
    ):
        media_control("stop", core)
        core.speak("Stopped.")
        return True

    if cmd in ("play pause", "toggle play", "toggle music", "toggle playback"):
        media_control("playpause", core)
        core.speak("Toggled.")
        return True

    if "play" in cmd and "pause" not in cmd:
        media_control("play", core)
        core.speak("Playing.")
        return True

    if "pause" in cmd:
        media_control("pause", core)
        core.speak("Paused.")
        return True

    if "next" in cmd or "skip" in cmd:
        media_control("next", core)
        core.speak("Next.")
        return True

    if "previous" in cmd or "back" in cmd:
        media_control("previous", core)
        core.speak("Previous.")
        return True

    return None
