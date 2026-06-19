"""Friendly, varied spoken phrases — the "voice UX" layer.

Every category holds several interchangeable lines so the assistant never sounds
robotic or repetitive. :func:`pick` remembers the last line used per category and
avoids repeating it back-to-back, so successive replies feel diverse.

Two roles are covered:
  * predecessor  — greetings spoken when the user just calls the wake word.
  * successor    — short acknowledgements spoken around a completed action.

``{user}`` in a template is filled with the user's name (from the OOBE) when one
is known; name-less variants are used otherwise.
"""

import random

# --- Predecessor: greetings (user said only the wake word) ------------------
_GREETINGS_NAMED = [
    "Hello, {user}!",
    "Hi {user}! How can I help?",
    "Hey {user}, what can I do for you?",
    "Yes, {user}?",
    "Hi there, {user}. I'm listening.",
    "Good to hear you, {user}. What do you need?",
    "At your service, {user}.",
]
_GREETINGS_PLAIN = [
    "Hello!",
    "Hi there! How can I help?",
    "Yes? I'm listening.",
    "Hey! What can I do for you?",
    "I'm here. What do you need?",
    "At your service.",
    "Go ahead, I'm listening.",
]

# --- Successor: lead-ins prefixed onto a positive confirmation --------------
_LEAD_INS = [
    "Sure!",
    "Certainly!",
    "Of course!",
    "Right away!",
    "On it!",
    "You got it!",
    "Absolutely!",
    "Okay!",
    "Will do!",
    "Happy to!",
    "No problem!",
    "Done and done —",
]

# --- Successor: generic "finished" when the action said nothing itself ------
_DONE = [
    "Done!",
    "All set.",
    "There you go.",
    "Finished.",
    "Taken care of.",
    "Got it.",
    "That's done.",
]

# --- Farewells --------------------------------------------------------------
_FAREWELLS = [
    "Goodbye!",
    "See you later!",
    "Take care!",
    "Bye for now!",
    "Talk to you soon!",
]
_FAREWELLS_NAMED = [
    "Goodbye, {user}!",
    "See you later, {user}!",
    "Take care, {user}!",
    "Bye for now, {user}!",
]

# --- Recovery: misheard / nothing heard -------------------------------------
_NOT_UNDERSTOOD = [
    "Sorry, I didn't catch that. Say help for commands.",
    "Hmm, I didn't get that one. Try saying help.",
    "I'm not sure what you mean. Say help to hear what I can do.",
    "I didn't quite understand. You can say help.",
]
_NO_INPUT = [
    "I didn't hear anything.",
    "Sorry, I missed that — go ahead.",
    "I didn't catch anything. I'm still listening.",
    "Hmm, nothing came through. Try again.",
]

_last = {}

# --- Yes / no recognition (shared by OOBE and the "did you mean?" recovery) --
# Kept liberal — Whisper mishears short words, so we accept many variants.
YES_WORDS = {
    "yes",
    "yeah",
    "yep",
    "yup",
    "sure",
    "okay",
    "ok",
    "correct",
    "right",
    "affirmative",
    "please",
    "do",
    "fine",
    "good",
    "keep",
    "definitely",
    "yance",
}
NO_WORDS = {
    "no",
    "nope",
    "nah",
    "negative",
    "don't",
    "dont",
    "change",
    "different",
    "other",
    "switch",
    "wrong",
    "cancel",
}


def wants_yes(text, default=True):
    """Interpret a spoken answer as yes/no. Unknown -> *default*."""
    words = set((text or "").lower().split())
    if words & NO_WORDS:
        return False
    if words & YES_WORDS:
        return True
    return default


def pick(options, key):
    """Choose a line from *options*, avoiding an immediate repeat per *key*."""
    if not options:
        return ""
    last = _last.get(key)
    choices = [o for o in options if o != last] or list(options)
    choice = random.choice(choices)
    _last[key] = choice
    return choice


def _fill(template, user):
    return template.format(user=user) if user else template


def greeting(user=None):
    if user:
        return _fill(pick(_GREETINGS_NAMED, "greet"), user)
    return pick(_GREETINGS_PLAIN, "greet")


def lead_in():
    return pick(_LEAD_INS, "lead")


def done():
    return pick(_DONE, "done")


def farewell(user=None):
    if user:
        return _fill(pick(_FAREWELLS_NAMED, "bye"), user)
    return pick(_FAREWELLS, "bye")


def not_understood():
    return pick(_NOT_UNDERSTOOD, "huh")


def no_input():
    return pick(_NO_INPUT, "noin")
