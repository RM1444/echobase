"""Tests for the OOBE recognition-profile picker (oobe._step_recognition).

The step is voice-driven, so we patch ``oobe._listen`` to feed spoken answers and
``builtins.input`` for the typed fallback; ``core`` is a plain Mock (only ``speak``
is exercised). Behaviour-only — no audio or Whisper is touched."""

from unittest.mock import Mock, patch

import pytest

from EchoBase.core import config, oobe


@pytest.mark.parametrize(
    ["text", "expected"],
    [
        ("two", 2),
        ("3", 3),
        ("four", 4),
        ("one", 1),
        ("to", 2),  # frequent Whisper homophone of "two"
        ("for", 4),
        ("free", 3),
        ("option 4 please", 4),
        ("five", None),
        ("9", None),  # out of range
        ("banana", None),
        ("", None),
    ],
)
def test_parse_choice(text, expected):
    assert oobe._parse_choice(text) == expected


@pytest.mark.parametrize(
    ["said", "profile"],
    [("two", 2), ("3", 3), ("four", 4), ("one", 1), ("to", 2), ("option 4", 4)],
)
def test_step_recognition_spoken_number(said, profile):
    core = Mock()
    cfg = {}
    with patch.object(oobe, "_listen", return_value=said):
        oobe._step_recognition(core, cfg)
    row = config.RECOGNITION_PROFILE_TABLE[profile]
    assert cfg["recognition_profile"] == profile
    assert cfg["whisper_model"] == row["model"]
    assert cfg["whisper_beam"] == row["beam"]
    core.speak.assert_called()  # menu + confirmation


def test_step_recognition_reprompts_on_unparseable_then_succeeds():
    core = Mock()
    cfg = {}
    answers = iter(["banana", "two"])
    with patch.object(oobe, "_listen", side_effect=lambda c, bias="": next(answers)):
        oobe._step_recognition(core, cfg)
    assert cfg["recognition_profile"] == 2


def test_step_recognition_keyboard_fallback():
    core = Mock()
    cfg = {}
    with (
        patch.object(oobe, "_listen", return_value=""),  # silence every attempt
        patch("builtins.input", return_value="3"),
    ):
        oobe._step_recognition(core, cfg)
    assert cfg["recognition_profile"] == 3
    assert cfg["whisper_model"] == "medium.en"


def test_step_recognition_defaults_to_balanced_when_nothing_understood():
    core = Mock()
    cfg = {}
    with (
        patch.object(oobe, "_listen", return_value=""),
        patch("builtins.input", return_value=""),
    ):
        oobe._step_recognition(core, cfg)
    assert cfg["recognition_profile"] == config.DEFAULT_RECOGNITION_PROFILE == 2
    assert cfg["whisper_model"] == "small.en"
    assert cfg["whisper_beam"] == 5


# --- _step_autostart --------------------------------------------------------


def test_step_autostart_yes_enables_and_writes_entry():
    core = Mock()
    cfg = {}
    with (
        patch.object(oobe, "_ask", return_value="yes"),
        patch.object(config, "set_autostart", return_value=True) as set_auto,
    ):
        oobe._step_autostart(core, cfg)
    set_auto.assert_called_once_with(True)
    assert cfg["start_on_boot"] is True


def test_step_autostart_no_disables():
    core = Mock()
    cfg = {}
    with (
        patch.object(oobe, "_ask", return_value="no"),
        patch.object(config, "set_autostart", return_value=True) as set_auto,
    ):
        oobe._step_autostart(core, cfg)
    set_auto.assert_called_once_with(False)
    assert cfg["start_on_boot"] is False


def test_step_autostart_defaults_to_off_on_silence():
    core = Mock()
    cfg = {}
    with (
        patch.object(oobe, "_ask", return_value=""),
        patch.object(config, "set_autostart", return_value=True) as set_auto,
    ):
        oobe._step_autostart(core, cfg)
    set_auto.assert_called_once_with(False)
    assert cfg["start_on_boot"] is False


def test_step_autostart_records_off_when_write_fails():
    """A wanted-but-failed setup leaves the preference off, matching reality."""
    core = Mock()
    cfg = {}
    with (
        patch.object(oobe, "_ask", return_value="yes"),
        patch.object(config, "set_autostart", return_value=False),
    ):
        oobe._step_autostart(core, cfg)
    assert cfg["start_on_boot"] is False
