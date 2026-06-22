"""Zero-touch error recovery + meta-commands (thesis section 2.1).

Covers what EchoBase actually implements:

* the difflib "did you mean ...?" recovery, with the three decision bands set by
  the active recognition profile (auto-run >= auto_cutoff, ask in
  [ask_cutoff, auto_cutoff), reject below);
* the ``listen_yes_no`` yes/no flow (YES_WORDS / NO_WORDS, "no" wins ties,
  default on unclear/silent);
* the meta-command vocabulary (wake-phrase stripping, stop/exit, per-mode cancel
  words).

It also documents -- behaviourally -- the design finding that EchoBase has **no
confirmation window before destructive actions**: routing any command never
invokes ``listen_yes_no``. The only yes/no flows are recovery and the OOBE wizard.
"""

from __future__ import annotations

import contextlib
import io

import pytest

from EchoBase.core import main as ebmain
from EchoBase.core import phrases as ebphrases
from validation.harness import metrics
from validation.harness.echobase_factory import (
    BLOCKING_MODE_NAMES,
    UNROUTED,
    phrase_origin_map,
    predict_route,
    predict_with_recovery,
)


# --------------------------------------------------------------------------- #
# listen_yes_no
# --------------------------------------------------------------------------- #


def _yes_no(fresh_core, transcript, default=None, first=b"\x00\x00"):
    """Drive the REAL listen_yes_no with a scripted transcript."""
    core = fresh_core()
    core.wait_for_speech = lambda *a, **k: first
    core.record_until_silence = lambda *a, **k: b""
    core.transcribe = lambda *a, **k: transcript
    return ebmain.EchoBase.listen_yes_no(core, "Did you mean, open firefox?", default=default)


class TestListenYesNo:
    def test_yes_words(self, fresh_core):
        for word in ("yes", "yeah", "sure", "correct", "okay"):
            assert _yes_no(fresh_core, word) is True, word

    def test_no_words(self, fresh_core):
        for word in ("no", "nope", "cancel", "wrong", "different"):
            assert _yes_no(fresh_core, word) is False, word

    def test_no_wins_ties(self, fresh_core):
        # When both a yes and a no word are heard, "no" wins (negative-safe).
        assert _yes_no(fresh_core, "yes no") is False

    def test_unclear_returns_default(self, fresh_core):
        assert _yes_no(fresh_core, "banana", default=False) is False
        assert _yes_no(fresh_core, "banana", default=True) is True

    def test_silence_returns_default(self, fresh_core):
        assert _yes_no(fresh_core, "anything", default=False, first=None) is False


# --------------------------------------------------------------------------- #
# "Did you mean ...?" recovery bands
# --------------------------------------------------------------------------- #

RECOVERY_INPUTS = [
    "open firefox",  # exact -> direct
    "opn firefox",  # tiny typo -> auto
    "opem fierfox",  # bigger typo
    "volyume up",
    "skroll down",
    "what is the time",
    "xqzptv",  # gibberish -> reject
    "asdfghjkl",
]


class TestRecoveryBands:
    def test_decision_consistent_with_cutoffs(self, core):
        import EchoBase.core.config as config

        settings = config.recognition_settings(core.config)
        rows = []
        with contextlib.redirect_stdout(io.StringIO()):
            for text in RECOVERY_INPUTS:
                plugin, decision, score = predict_with_recovery(core, text)
                rows.append(
                    {
                        "input": text,
                        "decision": decision,
                        "score": round(score, 3),
                        "routed_to": plugin,
                    }
                )
                # The band must follow from the score + the profile cutoffs.
                if decision == "auto":
                    assert score >= settings.auto_cutoff
                elif decision == "ask":
                    assert settings.ask_cutoff <= score < settings.auto_cutoff
                elif decision == "reject":
                    assert score < settings.ask_cutoff or plugin == UNROUTED
        metrics.write_report(
            "recovery_audit",
            rows,
            {
                "auto_cutoff": settings.auto_cutoff,
                "ask_cutoff": settings.ask_cutoff,
                "profile": core.config.get("recognition_profile"),
            },
            title="Fuzzy-recovery decision audit",
            caption="Section 2.1 -- difflib near-miss recovery decisions vs profile cutoffs.",
        )

    def test_exact_phrase_is_direct(self, core):
        with contextlib.redirect_stdout(io.StringIO()):
            _, decision, _ = predict_with_recovery(core, "open firefox")
        assert decision == "direct"

    def test_close_typo_auto_corrects(self, core):
        with contextlib.redirect_stdout(io.StringIO()):
            plugin, decision, score = predict_with_recovery(core, "opn firefox")
        assert decision == "auto" and plugin == "apps" and score >= 0.85

    def test_gibberish_rejected(self, core):
        with contextlib.redirect_stdout(io.StringIO()):
            _, decision, _ = predict_with_recovery(core, "xqzptv")
        assert decision == "reject"


# --------------------------------------------------------------------------- #
# Meta-commands: wake stripping, stop/exit, cancel vocab
# --------------------------------------------------------------------------- #


class TestMetaCommands:
    def test_route_clean_strips_wake_phrase(self, core):
        assert ebmain.EchoBase.route_clean(core, "Hey Jarvis, open firefox") == "open firefox"
        assert ebmain.EchoBase.route_clean(core, "jarvis scroll down") == "scroll down"

    def test_stop_exit_route_to_base(self, core):
        with contextlib.redirect_stdout(io.StringIO()):
            for word in ("stop", "exit", "quit"):
                assert predict_route(core, word) == "base", word

    def test_yes_no_vocabularies_present(self):
        assert {"yes", "yeah", "sure", "okay", "correct"} <= ebphrases.YES_WORDS
        assert {"no", "nope", "cancel", "wrong"} <= ebphrases.NO_WORDS

    def test_blocking_modes_have_cancel_vocabulary(self, core):
        """Each blocking mode must expose a stop/cancel exit vocabulary so a
        no-hands user can always leave a mode by voice."""
        mods = {p.NAME: p for p in core.plugins}
        # scroll's continuous loop, labels' picker and windows' picker each carry
        # a cancel/stop set; verify they contain the universal exit words.
        checks = {
            "scroll": "_STOP_WORDS",
            "labels": "_CANCEL",
            "windows": "_PICK_CANCEL",
        }
        for name, const in checks.items():
            mod = mods.get(name)
            if mod is None or not hasattr(mod, const):
                continue
            vocab = {w.lower() for w in getattr(mod, const)}
            assert vocab & {"stop", "cancel"}, f"{name}.{const} lacks stop/cancel"


# --------------------------------------------------------------------------- #
# Documented finding: NO destructive-action confirmation window
# --------------------------------------------------------------------------- #


def test_no_destructive_confirmation_window(fresh_core):
    """Routing ANY canonical command must never trigger a yes/no confirmation.

    This behaviourally documents the thesis limitation: lock/suspend/close/delete
    all execute immediately; the only listen_yes_no flows are fuzzy recovery and
    the OOBE wizard. If a confirmation gate is ever added, this test will flag it
    (and should then be updated to assert the gate fires for destructive ops).
    """
    core = fresh_core()
    calls = {"n": 0}

    def _spy(*_a, **_k):
        calls["n"] += 1
        return False

    core.listen_yes_no = _spy
    origin = phrase_origin_map(core)
    with contextlib.redirect_stdout(io.StringIO()):
        for phrase, owner in origin.items():
            if owner in BLOCKING_MODE_NAMES:
                continue
            predict_route(core, phrase)
    assert calls["n"] == 0, (
        "a command triggered a yes/no confirmation during direct routing -- "
        "EchoBase is documented as having no destructive-action confirmation window"
    )
