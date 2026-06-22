"""Build a real ``EchoBase`` instance with desktop side effects neutralised.

The validation logic tests need a *real* core (real plugins, the real 187-phrase
registry, the real fuzzy-recovery code) but must never actually click, type,
launch apps, call D-Bus or play TTS. This module constructs such an instance and
exposes a routing predictor used by the command-routing accuracy metric.

It deliberately does not mock the routing/recovery code under test -- only the
I/O boundary (``speak``, ``host_run``, ``subprocess``, and the listening
primitives so any in-mode listen loop exits immediately).
"""

from __future__ import annotations

import contextlib
from types import SimpleNamespace
from unittest.mock import patch

# Blocking "mode" plugins that run their own listen loop when triggered. The
# routing-accuracy metric covers one-shot commands and treats these specially
# (their trigger vocabulary is checked, not executed).
BLOCKING_MODE_NAMES = {"headtrack", "mousegrid", "browser", "dictation"}

UNROUTED = "(unrouted)"


def _ok_run(*_args, **_kwargs):
    """A successful host_run / subprocess.run result with empty output."""
    return SimpleNamespace(returncode=0, stdout="", stderr="")


@contextlib.contextmanager
def neutralized_subprocess():
    """Patch subprocess.run/Popen to no-ops, so plugins that shell out directly
    (not via core.host_run) never spawn real processes. Use around any path that
    calls the real ``route_command``/``_dispatch`` (which, unlike ``predict_route``,
    does not patch subprocess itself)."""
    with patch("subprocess.run", _ok_run), patch("subprocess.Popen", _ok_run):
        yield


def build_core(*, name: str = "Jarvis", recognition_profile: int = 2):
    """Return a real EchoBase with plugins loaded and all I/O neutralised.

    Heavy native deps (pyaudio/openwakeword/faster_whisper) must already be
    importable -- either really installed, or stubbed by the logic conftest.

    The recognition profile is pinned (default 2 = Balanced, the app's
    DEFAULT_RECOGNITION_PROFILE, cutoffs 0.85/0.6) so the fuzzy-recovery cutoffs
    are deterministic regardless of any saved ``~/.config/echobase/config.json``
    on the developer's machine -- essential for reproducible thesis numbers.
    """
    from EchoBase.core.main import EchoBase

    core = EchoBase(name=name)
    core.config["recognition_profile"] = recognition_profile
    core.load_plugins()

    # Neutralise the speech + shell boundary so matched commands run their
    # routing logic but produce no real side effects.
    core.speak = lambda *a, **k: None
    core.host_run = _ok_run
    core.flush_stream = lambda *a, **k: None
    core.type_text = lambda *a, **k: True
    # Make any in-mode listen loop terminate immediately by simulating the user
    # immediately saying a stop/cancel word. We must return a *truthy* first
    # frame: some loops (e.g. scroll.continuous_scroll) `continue` on an empty
    # frame and would otherwise spin forever; they only break once a transcript
    # contains a stop word.
    core.wait_for_speech = lambda *a, **k: b"\x00\x00"
    core.record_until_silence = lambda *a, **k: b""
    core.transcribe = lambda *a, **k: "stop cancel"
    core.transcribe_nbest = lambda *a, **k: "stop cancel"
    core.listen_yes_no = lambda *a, **k: False
    core.stream = SimpleNamespace(
        read=lambda *a, **k: b"\x00\x00",
        get_read_available=lambda *a, **k: 1024,
        stop_stream=lambda: None,
        close=lambda: None,
    )
    return core


def predict_route(core, text: str, *, include_blocking: bool = False) -> str:
    """Return the NAME of the plugin that handles *text*, or ``UNROUTED``.

    Mirrors ``EchoBase._dispatch``'s plugin loop (normalisation + first plugin to
    return non-None wins) without speaking the "didn't understand" reply and
    without the fuzzy recovery -- this measures the *direct* routing decision.
    By default blocking modes are skipped (they run their own loops); their
    recognition is tested separately via :func:`recognizes_trigger`.
    """
    normalized = core._normalize_command(text)
    with patch("subprocess.run", _ok_run), patch("subprocess.Popen", _ok_run):
        for plugin in core.plugins:
            name = getattr(plugin, "NAME", UNROUTED)
            if not include_blocking and name in BLOCKING_MODE_NAMES:
                continue
            result, timed_out = _call_handle(plugin, normalized, core)
            if timed_out:
                # The plugin entered a loop/mode -> it claimed the command.
                return name
            if result is not None:
                return name
    return UNROUTED


def _call_handle(plugin, cmd, core, timeout: float = 4.0):
    """Call ``plugin.handle`` under a watchdog. Returns (result, timed_out).

    A plugin that enters its own listen loop has matched the command; rather than
    risk hanging the suite if some loop ignores our stop-word escape hatch, we run
    it in a daemon thread and report a timeout as "claimed" (the daemon exits once
    it next reads our mocked stop transcript)."""
    import threading

    box: dict = {}

    def _target():
        try:
            box["result"] = plugin.handle(cmd, core)
        except Exception:  # a raising plugin is "not mine" for routing
            box["result"] = None

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        return None, True
    return box.get("result"), False


def phrase_origin_map(core) -> dict[str, str]:
    """Map each canonical phrase to the NAME of the plugin that *declared* it
    (first declarer wins, mirroring ``EchoBase._collect_phrases``).

    This is the authoritative routing ground truth for the command-routing
    accuracy metric: a phrase should route to the plugin that owns it.
    """
    origin: dict[str, str] = {}
    for plugin in core.plugins:
        items = getattr(plugin, "PHRASES", None)
        if not isinstance(items, (list, tuple)):
            items = []
            commands = getattr(plugin, "COMMANDS", None)
            if isinstance(commands, (list, tuple)):
                for line in commands:
                    if not isinstance(line, str):
                        continue
                    head = line.split(" - ")[0].split("/")[0].strip().lower()
                    if head and "[" not in head:
                        items.append(head)
        for phrase in items:
            if not isinstance(phrase, str):
                continue
            p = phrase.lower().strip()
            if p and p not in origin:
                origin[p] = getattr(plugin, "NAME", UNROUTED)
    return origin


def predict_with_recovery(core, text: str) -> tuple[str, str, float]:
    """Return (predicted_plugin, recovery_decision, closest_score) for *text*.

    recovery_decision is one of: "direct" (a plugin matched outright),
    "auto" (fuzzy auto-corrected >= auto_cutoff), "ask" (medium confidence),
    or "reject" (below ask_cutoff / nothing matched). Used by the recovery audit.
    """
    import EchoBase.core.config as config

    direct = predict_route(core, text)
    if direct != UNROUTED:
        return direct, "direct", 1.0

    guess, score = core._closest_phrase(core._normalize_command(text))
    settings = config.recognition_settings(core.config)
    if not guess or score < settings.ask_cutoff:
        return UNROUTED, "reject", score
    if score >= settings.auto_cutoff:
        return predict_route(core, guess), "auto", score
    return UNROUTED, "ask", score
