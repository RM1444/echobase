"""Tests for the global scroll plugin."""

from unittest.mock import patch

import pytest
from EchoBase.plugins import scroll


@pytest.mark.parametrize(
    ["cmd", "expected"],
    [
        ("scroll up", "up"),
        ("scroll down", "down"),
        ("scroll left", "left"),
        ("scroll right", "right"),
        ("scroll", "down"),  # default
    ],
)
def test_direction(cmd, expected):
    assert scroll._direction(cmd) == expected


@pytest.mark.parametrize(
    ["cmd", "expected"],
    [("scroll down", 3), ("scroll down five", 5), ("scroll up 8", 8)],
)
def test_amount(cmd, expected):
    assert scroll._amount(cmd) == expected


def test_non_scroll_returns_none(mock_core):
    scroll.setup(mock_core)
    assert scroll.handle("open files", mock_core) is None


@patch.object(scroll, "_scroll")
def test_single_scroll(mock_scroll, mock_core):
    scroll.setup(mock_core)
    assert scroll.handle("scroll down", mock_core) is True
    assert mock_scroll.call_args.args[0] == "down"


@patch.object(scroll, "continuous_scroll", return_value=True)
def test_continuous_trigger(mock_cont, mock_core):
    scroll.setup(mock_core)
    assert scroll.handle("keep scrolling down", mock_core) is True
    assert mock_cont.call_args.args[0] == "down"


def test_stop_scrolling_noop(mock_core):
    scroll.setup(mock_core)
    assert scroll.handle("stop scrolling", mock_core) is True


def test_point_prefers_tracking_pos(mock_core):
    scroll.setup(mock_core)
    mock_core._tracking_pos = (123, 456)
    assert scroll._point() == (123, 456)
