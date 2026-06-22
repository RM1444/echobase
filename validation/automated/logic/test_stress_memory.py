"""Stress & memory-stability check (thesis section 3.3).

Route 1000 consecutive scripted commands through the REAL dispatch+recovery
pipeline (``_dispatch`` with ``skip_blocking=True`` -- the same path EchoBase uses
for global commands, so the run never enters an interactive mode that would need
live audio) and verify memory does not grow unbounded after warmup (no leak).
This is the fast, mocked logic version; the companion ``harness/stress_runner.py``
adds real RAM/CPU sampling (psutil) for the headline thesis curve.

Marked ``slow`` so the default fast suite can deselect it with ``-m "not slow"``.
"""

from __future__ import annotations

import contextlib
import io
import tracemalloc

import pytest

from EchoBase.core import main as ebmain
from validation.harness import metrics
from validation.harness.echobase_factory import neutralized_subprocess

# Representative one-shot, non-blocking commands (no mode triggers, so
# route_command never enters a listen loop). A couple of near-misses exercise the
# fuzzy-recovery path too.
COMMAND_CYCLE = [
    "open firefox",
    "close firefox",
    "play",
    "pause",
    "volume up",
    "scroll down",
    "minimize",
    "maximize",
    "copy",
    "paste",
    "what day is it",
    "opn firefox",  # auto-recovered near-miss
    "xqzptv",  # rejected -> not understood
]

TOTAL = 1000
WARMUP = 100
GROWTH_LIMIT_KB = 512  # post-warmup net growth must stay well under this


@pytest.mark.slow
def test_thousand_commands_no_leak(fresh_core, results_dir):
    core = fresh_core()
    tracemalloc.start()
    curve = []

    with contextlib.redirect_stdout(io.StringIO()), neutralized_subprocess():
        baseline_kb = None
        for i in range(TOTAL):
            cmd = COMMAND_CYCLE[i % len(COMMAND_CYCLE)]
            ebmain.EchoBase._dispatch(core, cmd, skip_blocking=True)
            if i == WARMUP:
                baseline_kb = tracemalloc.get_traced_memory()[0] / 1024.0
            if i % 100 == 0 or i == TOTAL - 1:
                current_kb = tracemalloc.get_traced_memory()[0] / 1024.0
                curve.append({"command_index": i, "traced_kb": round(current_kb, 1)})

    final_kb = tracemalloc.get_traced_memory()[0] / 1024.0
    tracemalloc.stop()
    growth_kb = final_kb - (baseline_kb or final_kb)

    metrics.write_report(
        "stress_memory",
        curve,
        {
            "total_commands": TOTAL,
            "warmup": WARMUP,
            "baseline_kb": round(baseline_kb or 0.0, 1),
            "final_kb": round(final_kb, 1),
            "post_warmup_growth_kb": round(growth_kb, 1),
            "growth_limit_kb": GROWTH_LIMIT_KB,
            "verdict": "flat" if growth_kb < GROWTH_LIMIT_KB else "growing",
        },
        title="Memory stability over 1000 commands (traced heap)",
        caption="Section 3.3 -- post-warmup traced-heap growth; flat => no leak.",
        results_dir=results_dir,
    )
    assert growth_kb < GROWTH_LIMIT_KB, (
        f"post-warmup traced-heap growth {growth_kb:.1f} KB exceeds "
        f"{GROWTH_LIMIT_KB} KB -- possible leak"
    )


@pytest.mark.slow
def test_last_command_state_bounded(fresh_core):
    """Repeated routing must not accumulate unbounded per-command state."""
    core = fresh_core()
    with contextlib.redirect_stdout(io.StringIO()), neutralized_subprocess():
        for _ in range(200):
            ebmain.EchoBase._dispatch(core, "play", skip_blocking=True)
    # last_command holds a single string; the macro recorder is inactive.
    assert isinstance(core.last_command, (str, type(None)))
    assert core.recording is None
