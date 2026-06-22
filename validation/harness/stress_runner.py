"""Stress + memory/CPU sampling over many commands (thesis section 3.3).

Drives N consecutive scripted commands through the real dispatch+recovery
pipeline (``_dispatch`` with skip_blocking, under neutralised subprocess so no
real processes spawn) while sampling resident memory and CPU. Emits a memory
curve and a flat/growing verdict.

Uses psutil when available for RSS + CPU%; otherwise falls back to the standard
library ``resource`` module (peak RSS only). Importable and CLI-runnable:

    python -m validation.harness.stress_runner --count 1000
"""

from __future__ import annotations

import contextlib
import io
import os
import time

from validation.harness import metrics
from validation.harness.echobase_factory import neutralized_subprocess

COMMAND_CYCLE = [
    "open firefox", "close firefox", "play", "pause", "volume up", "scroll down",
    "minimize", "maximize", "copy", "paste", "what day is it", "opn firefox", "xqzptv",
]


def _sampler():
    """Return a callable -> (rss_mb, cpu_pct). Prefers psutil; falls back to
    resource.getrusage (rss only, cpu_pct = -1)."""
    try:
        import psutil

        proc = psutil.Process(os.getpid())
        proc.cpu_percent(None)  # prime

        def sample():
            return proc.memory_info().rss / (1024 * 1024), proc.cpu_percent(None)

        return sample, "psutil"
    except Exception:
        import resource

        def sample():
            rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            return rss_kb / 1024.0, -1.0  # ru_maxrss is KB on Linux

        return sample, "resource"


def run_stress(count: int = 1000, warmup: int = 100, sample_every: int = 50):
    """Run *count* commands; return (curve_rows, summary)."""
    from EchoBase.core import main as ebmain
    from validation.harness.echobase_factory import build_core

    core = build_core()
    sample, backend = _sampler()
    curve = []
    baseline_mb = None
    start = time.perf_counter()

    with contextlib.redirect_stdout(io.StringIO()), neutralized_subprocess():
        for i in range(count):
            ebmain.EchoBase._dispatch(core, COMMAND_CYCLE[i % len(COMMAND_CYCLE)],
                                      skip_blocking=True)
            if i == warmup:
                baseline_mb = sample()[0]
            if i % sample_every == 0 or i == count - 1:
                rss, cpu = sample()
                curve.append(
                    {
                        "command_index": i,
                        "rss_mb": round(rss, 2),
                        "cpu_pct": round(cpu, 1),
                        "elapsed_s": round(time.perf_counter() - start, 2),
                    }
                )

    final_mb = sample()[0]
    growth_mb = final_mb - (baseline_mb or final_mb)
    summary = {
        "backend": backend,
        "count": count,
        "warmup": warmup,
        "baseline_mb": round(baseline_mb or 0.0, 2),
        "final_mb": round(final_mb, 2),
        "post_warmup_growth_mb": round(growth_mb, 2),
        "throughput_cmd_per_s": round(count / (time.perf_counter() - start), 1),
        "verdict": "flat" if growth_mb < 50 else "growing",
    }
    return curve, summary


def _main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Stress + memory sampling over N commands.")
    ap.add_argument("--count", type=int, default=1000)
    ap.add_argument("--warmup", type=int, default=100)
    args = ap.parse_args(argv)

    curve, summary = run_stress(count=args.count, warmup=args.warmup)
    out = metrics.write_report(
        "stress_runtime",
        curve,
        summary,
        title="Stress: memory + CPU over commands",
        caption="Section 3.3 -- RSS/CPU curve over consecutive commands; flat => no leak.",
    )
    print(f"{summary['verdict']} | growth {summary['post_warmup_growth_mb']} MB "
          f"({summary['backend']}) | report: {out['md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
