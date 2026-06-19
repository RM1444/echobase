"""Personal text snippets — "type my email / phone / address / name".

A hands-free user can't easily dictate an email address or a street address
character by character. These shortcuts insert values collected once during the
OOBE (stored in the config) into the focused text field via AT-SPI, so common
personal details are one phrase away.
"""

from EchoBase.core import ui

NAME = "snippets"
DESCRIPTION = "Insert saved personal details into the focused field"

COMMANDS = [
    "type my email / type my phone / type my address / type my name",
]

PHRASES = [
    "type my email",
    "type my phone",
    "type my address",
    "type my name",
]

core = None

# Spoken field word -> config key holding the saved value.
_FIELDS = {
    "email": "snippet_email",
    "e-mail": "snippet_email",
    "mail": "snippet_email",
    "phone": "snippet_phone",
    "number": "snippet_phone",
    "address": "snippet_address",
    "name": "snippet_name",
}

_PREFIXES = ("type my ", "insert my ", "enter my ", "type out my ", "paste my ")


def setup(c):
    global core
    core = c


def handle(cmd, core):
    c = cmd.lower().strip(".,!? ")
    prefix = next((p for p in _PREFIXES if c.startswith(p)), None)
    if not prefix:
        return None

    field = c[len(prefix) :].strip()
    key = next((k for word, k in _FIELDS.items() if word in field), None)
    if not key:
        return None

    value = (getattr(core, "config", {}) or {}).get(key, "")
    if not value:
        core.speak(f"You haven't set up your {field}. You can add it in setup.")
        return True

    ui.log("snippet", f"{field} -> focused field", ui.CYAN)
    if core.type_text(value):
        core.speak(f"Typed your {field}.")
    else:
        core.speak("No text field is focused.")
    return True
