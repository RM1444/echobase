"""Command-routing accuracy (thesis section 1.2 -- reframed from NLU intents).

EchoBase has no intent/slot extraction: "understanding" is exact/substring
matching inside each plugin's ``handle`` plus a difflib fuzzy fallback. The
meaningful analog of intent accuracy is therefore *routing accuracy*: does a
spoken command reach the plugin that owns it?

Ground truth is each plugin's own canonical vocabulary (its ``PHRASES`` list, or
the heads of its ``COMMANDS`` help lines) -- the forms the author intends to
trigger that plugin. We route every canonical phrase through the real dispatch
loop (``predict_route``) and compute per-plugin Precision/Recall/F1 plus overall
accuracy, writing a thesis-ready report to ``validation/results/``.

Blocking "mode" plugins (head tracking, mouse grid, browser, dictation) run
their own listen loops on trigger, so they are excluded from the executed
routing set and their trigger recognition is checked separately.
"""

from __future__ import annotations

import contextlib
import io

import pytest

from validation.harness import metrics
from validation.harness.echobase_factory import (
    BLOCKING_MODE_NAMES,
    UNROUTED,
    phrase_origin_map,
    predict_route,
)

# Known, documented routing collisions (genuine findings, not test flakiness).
# The match-order router lets an earlier plugin's substring win: media matches
# the bare words "next"/"previous" (for next/previous track) and so shadows the
# window/windows commands that begin with them. Reported in the thesis as a
# substring-precedence limitation of the match-order router.
KNOWN_COLLISIONS = {
    "next workspace": "media",
    "previous workspace": "media",
    "next window": "media",
    "previous window": "media",
}

# Registry-hygiene finding: files.py's COMMANDS includes two *descriptive*
# continuation lines ("Folders: documents, ...") that have no " - " separator and
# no "[placeholder]", so _collect_phrases mistakes them for command phrases and
# adds them to the 187-entry fuzzy-recovery vocabulary. They are not real
# commands and do not route anywhere meaningful. Documented, not a routing defect.
KNOWN_REGISTRY_ARTIFACTS = {
    "folders: documents, downloads, pictures, screenshots, music, videos,",
    "home, desktop, config, trash, projects, code, root, tmp",
}

# Plugins whose real commands are argument-based (e.g. "open downloads") and so
# are not present in the canonical vocabulary as discrete phrases. Their routing
# is exercised in test_integration.py instead.
ARG_BASED_PLUGINS = {"files"}


def _routing_dataset(core):
    """Return [(phrase, expected_plugin)] for all non-blocking canonical phrases."""
    origin = phrase_origin_map(core)
    return [
        (phrase, owner)
        for phrase, owner in origin.items()
        if owner not in BLOCKING_MODE_NAMES
    ]


def _evaluate(core):
    dataset = _routing_dataset(core)
    pairs = []
    rows = []
    with contextlib.redirect_stdout(io.StringIO()):  # silence plugin help/prints
        for phrase, expected in dataset:
            predicted = predict_route(core, phrase)
            pairs.append((expected, predicted if predicted != UNROUTED else None))
            rows.append(
                {
                    "phrase": phrase,
                    "expected_plugin": expected,
                    "predicted_plugin": predicted,
                    "correct": predicted == expected,
                }
            )
    report = metrics.classification_report(pairs)
    return dataset, rows, report


@pytest.fixture(scope="module")
def routing(core):
    return _evaluate(core)


def test_writes_routing_report(routing, results_dir):
    dataset, rows, report = routing
    per_class_rows = report.rows()
    metrics.write_report(
        "routing_accuracy",
        rows,
        {
            "n_phrases": len(dataset),
            "accuracy": round(report.accuracy, 4),
            "macro_f1": round(report.macro_f1, 4),
            "micro_f1": round(report.micro_f1, 4),
        },
        title="Command-routing accuracy (per phrase)",
        caption="Section 1.2 -- routing of canonical command phrases to owning plugin.",
        results_dir=results_dir,
    )
    metrics.write_report(
        "routing_per_plugin",
        per_class_rows,
        {"macro_f1": round(report.macro_f1, 4)},
        title="Command-routing Precision/Recall/F1 per plugin",
        caption="Section 1.2 -- per-plugin routing quality.",
        results_dir=results_dir,
    )
    assert (results_dir / "routing_accuracy.md").exists()


def test_routing_accuracy_above_threshold(routing):
    dataset, rows, report = routing
    # Account for the documented collisions: anything misrouted that isn't a
    # known collision is a regression.
    unexpected = [
        r
        for r in rows
        if not r["correct"]
        and KNOWN_COLLISIONS.get(r["phrase"]) != r["predicted_plugin"]
    ]
    assert report.accuracy >= 0.85, (
        f"routing accuracy {report.accuracy:.2%} below 85%; "
        f"unexpected misroutes: {[r['phrase'] for r in unexpected][:10]}"
    )


def test_no_undocumented_misroutes(routing):
    """Every misroute must be an already-documented collision or registry
    artifact -- this is the regression guard."""
    _dataset, rows, _report = routing
    undocumented = [
        r
        for r in rows
        if not r["correct"]
        and r["phrase"] not in KNOWN_REGISTRY_ARTIFACTS
        and KNOWN_COLLISIONS.get(r["phrase"]) != r["predicted_plugin"]
    ]
    assert not undocumented, (
        "undocumented routing collisions (update KNOWN_COLLISIONS or fix routing): "
        + ", ".join(f"{r['phrase']!r}->{r['predicted_plugin']}" for r in undocumented)
    )


def test_every_nonblocking_plugin_owns_at_least_one_route(routing):
    _dataset, _rows, report = routing
    # Each plugin that declares real (non-arg-based) vocabulary must be reachable.
    unreachable = [
        c.label
        for c in report.per_class.values()
        if c.support and c.recall == 0 and c.label not in ARG_BASED_PLUGINS
    ]
    assert not unreachable, f"plugins with zero reachable phrases: {unreachable}"


def test_blocking_mode_triggers_are_recognized(core):
    """Blocking modes are excluded from execution, but their trigger phrases must
    still be present in the canonical vocabulary (so they are routable)."""
    origin = phrase_origin_map(core)
    by_owner: dict[str, list[str]] = {}
    for phrase, owner in origin.items():
        by_owner.setdefault(owner, []).append(phrase)
    for mode in BLOCKING_MODE_NAMES:
        assert by_owner.get(mode), f"blocking mode {mode!r} declares no trigger phrases"
