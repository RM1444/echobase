import datetime

NAME = "time"
DESCRIPTION = "Spoken time, date, and day"

COMMANDS = [
    "what time / time - speak the current time",
    "what date / date - speak today's date",
    "what day - speak the current day of the week",
]

# Canonical spoken forms for the fuzzy near-miss recovery (main._recover).
PHRASES = ["what time", "what date", "what day"]

core = None


def setup(c):
    global core
    core = c


def handle(cmd, core):
    c = cmd.lower().strip()

    if c in (
        "what time",
        "what's the time",
        "whats the time",
        "current time",
        "tell me the time",
        "time",
        "the time",
    ):
        now = datetime.datetime.now()
        core.speak(now.strftime("It is %-I:%M %p."))
        return True

    if c in (
        "what date",
        "what's the date",
        "whats the date",
        "today's date",
        "todays date",
        "current date",
        "date",
        "the date",
    ):
        today = datetime.date.today()
        core.speak(today.strftime("Today is %A, %B %-d, %Y."))
        return True

    if c in (
        "what day",
        "what's the day",
        "whats the day",
        "what day is it",
        "day of the week",
    ):
        core.speak(datetime.date.today().strftime("It is %A."))
        return True

    return None
