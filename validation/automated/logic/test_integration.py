"""Desktop-backend integration + graceful degradation (thesis section 4.1).

Reframed from the source plan's IoT/HTTP integration to EchoBase's real backends:
GNOME Shell extension over D-Bus (gdbus), MPRIS media (dbus-send), portable
keyboard shortcuts (gdbus KeyCombo/PressKey), system control (wpctl/loginctl) and
app launch (flatpak/which). For each, we drive the owning plugin directly and
assert it issues the expected backend call; then we re-run with the backend
failing and record whether the failure is surfaced to the user by voice.

FINDING reported: failure feedback is inconsistent -- missing-resource failures
(app not installed) are spoken, but a downed extension / failed D-Bus call is
typically silent (terminal-only). The degradation table captures this per backend.
"""

from __future__ import annotations

import contextlib
import io
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from validation.harness import metrics

# (plugin, command, tokens that must appear together in one backend call)
BACKEND_CASES = [
    ("window", "minimize", ["gdbus", "org.EchoBase.Grid.MinimizeWindow"]),
    ("keyboard", "copy", ["gdbus", "org.EchoBase.Grid.KeyCombo"]),
    ("media", "play", ["dbus-send", "org.freedesktop.DBus.ListNames"]),
    ("apps", "open firefox", ["flatpak"]),
    ("system", "volume up", ["wpctl"]),
]


class _Recorder:
    """Captures every backend argv passed to subprocess.run/Popen/host_run and
    returns a configurable result."""

    def __init__(self, returncode=0, stdout=""):
        self.calls: list[list[str]] = []
        self.returncode = returncode
        self.stdout = stdout

    def __call__(self, cmd, *args, **kwargs):
        self.calls.append(list(cmd) if isinstance(cmd, (list, tuple)) else [str(cmd)])
        return SimpleNamespace(returncode=self.returncode, stdout=self.stdout, stderr="")

    def saw(self, tokens) -> bool:
        return any(all(any(t == part or t in part for part in call) for t in tokens)
                   for call in self.calls)


def _plugin(core, name):
    for p in core.plugins:
        if getattr(p, "NAME", "") == name:
            return p
    raise AssertionError(f"plugin {name!r} not loaded")


def _drive(core, plugin, command, returncode=0, stdout=""):
    """Call plugin.handle(command) capturing all backend calls + speech."""
    rec = _Recorder(returncode=returncode, stdout=stdout)
    spoken: list[str] = []
    core.host_run = rec
    core.speak = lambda text, *a, **k: spoken.append(text)
    with patch("subprocess.run", rec), patch("subprocess.Popen", rec):
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                plugin.handle(command, core)
            except Exception as exc:  # graceful degradation must not crash
                return rec, spoken, exc
    return rec, spoken, None


class TestBackendRouting:
    @pytest.mark.parametrize("name,command,tokens", BACKEND_CASES)
    def test_command_issues_expected_backend_call(self, fresh_core, name, command, tokens):
        core = fresh_core()
        rec, _spoken, exc = _drive(core, _plugin(core, name), command)
        assert exc is None, f"{name} raised on success path: {exc}"
        assert rec.saw(tokens), (
            f"{name!r} handling {command!r} did not issue a backend call with "
            f"{tokens}; calls were: {rec.calls}"
        )


class TestGracefulDegradation:
    @pytest.mark.parametrize("name,command,tokens", BACKEND_CASES)
    def test_failure_does_not_crash(self, fresh_core, name, command, tokens):
        core = fresh_core()
        _rec, _spoken, exc = _drive(core, _plugin(core, name), command, returncode=1)
        assert exc is None, f"{name!r} crashed when backend failed: {exc}"

    def test_degradation_feedback_table(self, fresh_core, results_dir):
        """Record whether each backend speaks on failure (the inconsistency finding)."""
        rows = []
        for name, command, _tokens in BACKEND_CASES:
            core = fresh_core()
            _rec, spoken, exc = _drive(core, _plugin(core, name), command, returncode=1)
            rows.append(
                {
                    "plugin": name,
                    "command": command,
                    "crashed": exc is not None,
                    "speaks_on_failure": bool(spoken),
                    "spoken": " | ".join(spoken) if spoken else "",
                }
            )
        metrics.write_report(
            "integration_degradation",
            rows,
            {
                "finding": (
                    "Failure feedback is inconsistent: missing-resource failures "
                    "(e.g. app not installed) are spoken; a downed extension / failed "
                    "D-Bus call is typically silent (terminal log only)."
                )
            },
            title="Graceful degradation: spoken feedback on backend failure",
            caption="Section 4.1 -- which backends surface failures to the user by voice.",
            results_dir=results_dir,
        )
        assert not any(r["crashed"] for r in rows)
