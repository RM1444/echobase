"""Tests for the multitasking / suggestion / helper features added to core."""

import sys
from unittest.mock import MagicMock, Mock

import pytest

# Mock heavy external deps before importing main (mirrors test_main.py).
sys.modules.setdefault("pyaudio", MagicMock())
sys.modules.setdefault("openwakeword", MagicMock())
sys.modules.setdefault("openwakeword.model", MagicMock())
sys.modules.setdefault("openwakeword.vad", MagicMock())
sys.modules.setdefault("faster_whisper", MagicMock())

from EchoBase.core import config  # noqa: E402
from EchoBase.core.main import EchoBase  # noqa: E402


def _plugin(name, result):
    p = Mock()
    p.NAME = name
    p.handle = Mock(return_value=result)
    return p


# --- _collect_phrases --------------------------------------------------------


def test_collect_phrases_uses_PHRASES_and_COMMANDS():
    app = EchoBase()
    p1 = Mock(spec=["NAME", "PHRASES", "handle"])
    p1.NAME = "a"
    p1.PHRASES = ["open files", "lock screen"]
    p2 = Mock(spec=["NAME", "COMMANDS", "handle"])
    p2.NAME = "b"
    p2.COMMANDS = ["volume up - raise volume", "[number] - placeholder"]
    app.plugins = [p1, p2]
    app._collect_phrases()
    assert "open files" in app.known_phrases
    assert "volume up" in app.known_phrases
    # Placeholder help lines are ignored.
    assert all("[" not in p for p in app.known_phrases)


# --- run_global_command (skips blocking modes) -------------------------------


def test_run_global_command_skips_blocking_plugin():
    app = EchoBase()
    blocking = _plugin("headtrack", True)
    normal = _plugin("system", True)
    app.plugins = [blocking, normal]

    assert app.run_global_command("volume up") is True
    blocking.handle.assert_not_called()
    normal.handle.assert_called_once()


def test_run_global_command_unmatched_is_quiet():
    app = EchoBase()
    app.plugins = [_plugin("system", None)]
    app.speak = Mock()
    assert app.run_global_command("flibbertigibbet") is None
    app.speak.assert_not_called()


# --- listen_yes_no -----------------------------------------------------------


def _audio_core():
    app = EchoBase()
    app.speak = Mock()
    app.flush_stream = Mock()
    app.wait_for_speech = Mock(return_value=b"a")
    app.record_until_silence = Mock(return_value=b"b")
    return app


def test_listen_yes_no_yes():
    app = _audio_core()
    app.transcribe = Mock(return_value="yes please")
    assert app.listen_yes_no("ok?") is True


def test_listen_yes_no_no():
    app = _audio_core()
    app.transcribe = Mock(return_value="no thanks")
    assert app.listen_yes_no("ok?") is False


def test_listen_yes_no_silence_returns_default():
    app = _audio_core()
    app.wait_for_speech = Mock(return_value=None)
    assert app.listen_yes_no("ok?", default=False) is False


# --- normalization -----------------------------------------------------------


def test_normalize_strips_filler():
    assert EchoBase._normalize_command("please open files") == "open files"
    assert EchoBase._normalize_command("open files please") == "open files"
    assert EchoBase._normalize_command("could you open files thanks") == "open files"
    assert EchoBase._normalize_command("  volume   up ") == "volume up"


# --- _closest_phrase ---------------------------------------------------------


def test_closest_phrase_picks_best():
    app = EchoBase()
    app.known_phrases = ["open firefox", "volume up", "what time"]
    phrase, score = app._closest_phrase("open fire fox")
    assert phrase == "open firefox"
    assert score > 0.85


def test_closest_phrase_empty():
    app = EchoBase()
    app.known_phrases = []
    assert app._closest_phrase("anything") == (None, 0.0)


# --- _recover (auto-run vs ask) ----------------------------------------------


def test_recover_auto_runs_very_close_match():
    app = EchoBase()
    app.config = {}  # default cutoffs (0.85/0.6), independent of any saved profile
    app.known_phrases = ["open firefox"]
    app.listen_yes_no = Mock()
    app._dispatch = Mock(return_value=True)
    # "open fire fox" is ~0.9 similar -> auto-run, no prompt.
    assert app._recover("open fire fox", False, True) is True
    app.listen_yes_no.assert_not_called()
    assert app._dispatch.call_args.args[0] == "open firefox"


def test_recover_asks_on_medium_match():
    app = EchoBase()
    app.config = {}  # default cutoffs (0.85/0.6), independent of any saved profile
    # Craft a phrase in the 0.6-0.85 band relative to the input.
    app.known_phrases = ["brightness up"]
    app.listen_yes_no = Mock(return_value=True)
    app._dispatch = Mock(return_value=True)
    guess, score = app._closest_phrase("brightnes up now")
    assert 0.6 <= score < 0.85  # sanity: this is the "ask" band
    app._recover("brightnes up now", False, True)
    app.listen_yes_no.assert_called_once()


def test_recover_quiet_midmode_on_medium():
    app = EchoBase()
    app.config = {}  # default cutoffs (0.85/0.6), independent of any saved profile
    app.known_phrases = ["brightness up"]
    app.listen_yes_no = Mock()
    # announce_unknown=False (mid-mode) -> no prompt on a medium match.
    assert app._recover("brightnes up now", True, False) is None
    app.listen_yes_no.assert_not_called()


def test_recover_no_match_returns_none():
    app = EchoBase()
    app.config = {}  # default cutoffs (0.85/0.6), independent of any saved profile
    app.known_phrases = ["volume up"]
    assert app._recover("xyzzy plugh", False, True) is None


# --- type_text ---------------------------------------------------------------


def test_type_text_delegates_to_atspi(monkeypatch):
    app = EchoBase()
    called = {}

    def fake_insert(t):
        called["t"] = t
        return True

    monkeypatch.setattr("EchoBase.core.main.atspi.insert_text", fake_insert)
    assert app.type_text("hello") is True
    assert called["t"] == "hello"


# --- config: browser detection ----------------------------------------------


def test_browser_command_prefers_saved(monkeypatch):
    monkeypatch.setattr(config.shutil, "which", lambda b: "/usr/bin/" + b)
    assert config.browser_command({"browser": "firefox"}) == "firefox"


def test_browser_command_falls_back_to_installed(monkeypatch):
    monkeypatch.setattr(
        config.shutil, "which", lambda b: "/usr/bin/" + b if b == "firefox" else None
    )
    assert config.browser_command({"browser": ""}) == "firefox"


def test_browser_command_xdg_open_when_none(monkeypatch):
    monkeypatch.setattr(config.shutil, "which", lambda b: None)
    assert config.browser_command({"browser": ""}) == "xdg-open"


def test_detect_browsers(monkeypatch):
    monkeypatch.setattr(
        config.shutil, "which", lambda b: "/usr/bin/x" if b == "google-chrome" else None
    )
    assert config.detect_browsers() == [("chrome", "google-chrome")]


# --- config: recognition + pace helpers --------------------------------------


def test_recognition_settings_defaults():
    # No profile chosen yet (fresh boot) -> legacy fast path, today's behaviour.
    s = config.recognition_settings({})
    assert (s.model, s.beam) == ("base.en", 1)
    assert s.bias == "command"
    assert (s.auto_cutoff, s.ask_cutoff, s.nbest) == (0.85, 0.6, 1)


def test_recognition_settings_legacy_keys_still_work():
    # A config saved before profiles existed runs identically to before.
    s = config.recognition_settings({"whisper_model": "small.en", "whisper_beam": 5})
    assert (s.model, s.beam) == ("small.en", 5)
    assert s.bias == "command"
    assert (s.auto_cutoff, s.ask_cutoff, s.nbest) == (0.85, 0.6, 1)


def test_recognition_settings_bad_beam_falls_back():
    assert config.recognition_settings({"whisper_beam": "oops"}).beam == 1


@pytest.mark.parametrize(
    ["profile", "model", "beam", "bias", "auto", "ask", "nbest"],
    [
        (1, "base.en", 1, "command", 0.85, 0.6, 1),
        (2, "small.en", 5, "command", 0.85, 0.6, 1),
        (3, "medium.en", 8, "phrases", 0.80, 0.55, 1),
        (4, "distil-large-v3", 8, "phrases-strong", 0.72, 0.50, 3),
    ],
)
def test_recognition_settings_profile_expansion(
    profile, model, beam, bias, auto, ask, nbest
):
    s = config.recognition_settings({"recognition_profile": profile})
    assert s.model == model
    assert s.beam == beam
    assert s.bias == bias
    assert s.auto_cutoff == auto
    assert s.ask_cutoff == ask
    assert s.nbest == nbest


def test_profile_1_and_2_match_legacy_exactly():
    # Profiles 1/2 must reproduce the old fast/accurate behaviour exactly.
    p1 = config.recognition_settings({"recognition_profile": 1})
    legacy_fast = config.recognition_settings(
        {"whisper_model": "base.en", "whisper_beam": 1}
    )
    assert p1 == legacy_fast
    p2 = config.recognition_settings({"recognition_profile": 2})
    legacy_accurate = config.recognition_settings(
        {"whisper_model": "small.en", "whisper_beam": 5}
    )
    assert p2 == legacy_accurate


@pytest.mark.parametrize(
    ["cfg", "expected"],
    [
        ({"recognition_profile": 3}, 3),
        ({"whisper_model": "base.en"}, 1),
        ({"whisper_model": "small.en"}, 2),
        ({"whisper_model": "medium.en"}, 3),
        ({"whisper_model": "distil-large-v3"}, 4),
        ({"whisper_model": "large-v3"}, 4),
        ({}, 1),
    ],
)
def test_profile_for_config_reverse_maps(cfg, expected):
    assert config.profile_for_config(cfg) == expected


@pytest.mark.parametrize(
    ["pace", "expected"],
    [
        ("normal", (0.6, 8.0)),
        ("relaxed", (1.0, 11.0)),
        ("slow", (1.4, 14.0)),
        ("unknown", (0.6, 8.0)),
    ],
)
def test_pace_timing(pace, expected):
    assert config.pace_timing({"speech_pace": pace}) == expected


# --- recognition profile: runtime wiring -------------------------------------


def test_recover_uses_profile_cutoffs():
    # Profile 4 relaxes auto-run to 0.72, so a 0.78 near-miss runs silently.
    app = EchoBase()
    app.config = {"recognition_profile": 4}
    app.known_phrases = ["volume up"]
    app._closest_phrase = Mock(return_value=("volume up", 0.78))
    app._dispatch = Mock(return_value=True)
    app.listen_yes_no = Mock()
    assert app._recover("vol up", False, True) is True
    app.listen_yes_no.assert_not_called()
    app._dispatch.assert_called_once()


def test_recover_default_cutoffs_for_legacy():
    # Same 0.78 match under the defaults (0.85 auto) only earns a "did you mean".
    app = EchoBase()
    app.config = {}
    app.known_phrases = ["volume up"]
    app._closest_phrase = Mock(return_value=("volume up", 0.78))
    app._dispatch = Mock(return_value=True)
    app.listen_yes_no = Mock(return_value=False)
    app.speak = Mock()
    app._recover("vol up", False, True)
    app.listen_yes_no.assert_called_once()


def test_command_prompt_command_bias_is_plain():
    from EchoBase.core.main import COMMAND_PROMPT

    app = EchoBase()
    app.config = {"recognition_profile": 1}
    app.known_phrases = ["scroll down", "open files"]
    assert app._command_prompt() == COMMAND_PROMPT


def test_command_prompt_phrases_bias_enumerates_vocab():
    app = EchoBase()
    app.config = {"recognition_profile": 3}
    app.known_phrases = ["scroll down", "open files"]
    prompt = app._command_prompt()
    assert "scroll down" in prompt and "open files" in prompt


def test_transcribe_nbest_collects_distinct(monkeypatch):
    app = EchoBase()
    app.config = {"audio_preprocessing": False, "recognition_profile": 4}
    app.known_phrases = []
    app._audio_to_wav = Mock(return_value="/tmp/x.wav")
    monkeypatch.setattr("EchoBase.core.main.os.remove", lambda p: None)
    texts = iter(["scroll down", "scroll down", "scroll lown"])

    def fake_transcribe(path, **kw):
        seg = Mock()
        seg.text = next(texts)
        return ([seg], None)

    app.whisper = Mock()
    app.whisper.transcribe = Mock(side_effect=fake_transcribe)
    out = app.transcribe_nbest(b"x", n=3)
    assert out == ["scroll down", "scroll lown"]  # distinct, order preserved


def test_pick_best_candidate_prefers_closest_phrase():
    app = EchoBase()
    app.known_phrases = ["scroll down"]
    assert app._pick_best_candidate(["scroll lown", "scroll down"]) == "scroll down"


def test_pick_best_candidate_ties_keep_primary():
    app = EchoBase()
    app.known_phrases = []  # every candidate scores 0.0 -> tie -> keep first
    assert app._pick_best_candidate(["first", "second"]) == "first"


def test_pick_best_candidate_empty():
    app = EchoBase()
    app.known_phrases = ["x"]
    assert app._pick_best_candidate([]) == ""


def test_ensure_whisper_model_no_reload_when_same(monkeypatch):
    app = EchoBase()
    app.config = {"recognition_profile": 1}
    app.whisper = object()
    app._whisper_model_name = "base.en"
    app.speak = Mock()
    made = {}
    monkeypatch.setattr(
        "EchoBase.core.main.WhisperModel",
        lambda m, compute_type="int8": made.setdefault("m", m),
    )
    app._ensure_whisper_model()
    assert "m" not in made
    app.speak.assert_not_called()


def test_ensure_whisper_model_reloads_and_warns_for_heavy(monkeypatch):
    app = EchoBase()
    app.config = {"recognition_profile": 4}  # distil-large-v3 (heavy)
    app.whisper = None
    app._whisper_model_name = None
    app.speak = Mock()
    monkeypatch.setattr(
        "EchoBase.core.main.WhisperModel", lambda m, compute_type="int8": "M"
    )
    app._ensure_whisper_model()
    assert app._whisper_model_name == "distil-large-v3"
    app.speak.assert_called_once()  # "this may take a moment"


def test_ensure_whisper_model_light_profile_is_quiet(monkeypatch):
    app = EchoBase()
    app.config = {"recognition_profile": 2}  # small.en (not heavy)
    app.whisper = None
    app._whisper_model_name = None
    app.speak = Mock()
    monkeypatch.setattr(
        "EchoBase.core.main.WhisperModel", lambda m, compute_type="int8": "M"
    )
    app._ensure_whisper_model()
    assert app._whisper_model_name == "small.en"
    app.speak.assert_not_called()
