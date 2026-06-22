"""Standalone command-routing accuracy report (thesis section 1.2).

Runs every canonical command phrase through the real dispatch loop and writes the
per-phrase and per-plugin Precision/Recall/F1 reports to ``validation/results/``.
This is the CLI twin of ``automated/logic/test_command_routing.py`` for ad-hoc
runs and for regenerating the thesis tables.

    python -m validation.harness.routing_eval
"""

from __future__ import annotations

import contextlib
import io

from validation.harness import metrics
from validation.harness.echobase_factory import (
    BLOCKING_MODE_NAMES,
    UNROUTED,
    build_core,
    phrase_origin_map,
    predict_route,
)


def evaluate(core=None):
    core = core or build_core()
    origin = phrase_origin_map(core)
    pairs, rows = [], []
    with contextlib.redirect_stdout(io.StringIO()):
        for phrase, owner in origin.items():
            if owner in BLOCKING_MODE_NAMES:
                continue
            predicted = predict_route(core, phrase)
            pairs.append((owner, predicted if predicted != UNROUTED else None))
            rows.append(
                {
                    "phrase": phrase,
                    "expected_plugin": owner,
                    "predicted_plugin": predicted,
                    "correct": predicted == owner,
                }
            )
    report = metrics.classification_report(pairs)
    return rows, report


def _main(argv=None) -> int:
    rows, report = evaluate()
    metrics.write_report(
        "routing_accuracy",
        rows,
        {
            "n_phrases": len(rows),
            "accuracy": round(report.accuracy, 4),
            "macro_f1": round(report.macro_f1, 4),
            "micro_f1": round(report.micro_f1, 4),
        },
        title="Command-routing accuracy (per phrase)",
        caption="Section 1.2 -- routing of canonical command phrases to owning plugin.",
    )
    out = metrics.write_report(
        "routing_per_plugin",
        report.rows(),
        {"macro_f1": round(report.macro_f1, 4)},
        title="Command-routing Precision/Recall/F1 per plugin",
        caption="Section 1.2 -- per-plugin routing quality.",
    )
    print(f"routing accuracy {report.accuracy:.2%} over {len(rows)} phrases | "
          f"report: {out['md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
