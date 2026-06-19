"""Tests for the core main module."""

import os
import shutil
import sys
from importlib import import_module
from unittest.mock import MagicMock, call, patch


def test_dunder_main_module():
    """Exercise (most of) the code in the ``__main__`` module."""
    import_module("EchoBase.core.__main__")


def test_entrypoint():
    """Is entrypoint script installed? (pyproject.toml)"""
    assert shutil.which("EchoBase")


@patch("EchoBase.core.main.EchoBase")
def test_main_run(mock_EchoBase):
    """Does main:run instantiate the EchoBase class and run its method?"""
    sys.modules["pyaudio"] = MagicMock()
    from EchoBase.core import main

    # run() now parses argv (--name / --reset-oobe) and honours ECHOBASE_RESET;
    # give it a clean argv/env so argparse doesn't choke on pytest's arguments.
    with patch.object(sys, "argv", ["EchoBase"]), patch.dict(
        os.environ, {}, clear=True
    ):
        main.run()

    assert mock_EchoBase.mock_calls == [
        call(name=None, reset_oobe=False),
        call().run(),
    ]
