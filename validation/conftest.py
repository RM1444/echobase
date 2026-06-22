"""Shared fixtures for the EchoBase validation suite.

This conftest is intentionally light: it only puts the repository root on
``sys.path`` (so ``import validation.harness...`` works regardless of the
invocation directory) and exposes the results directory. The heavy-dependency
stubbing lives in ``automated/logic/conftest.py`` so it never leaks into the
``automated/realmodel/`` tests, which need the real stack.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


@pytest.fixture(scope="session")
def results_dir() -> Path:
    """The directory where run artifacts (CSV/JSON/MD) are written."""
    from validation.harness import metrics

    metrics.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    return metrics.RESULTS_DIR
