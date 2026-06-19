"""Tests for the labels plugin (click-by-name and number parsing)."""

from unittest.mock import patch

import pytest
from EchoBase.plugins import labels


@pytest.mark.parametrize(
    ["text", "expected"],
    [("three", 3), ("zero two", 2), ("seven", 7), ("nothing", None)],
)
def test_parse_number(text, expected):
    assert labels.parse_number(text) == expected


@patch.object(labels, "_ext")
@patch.object(labels, "get_clickables")
def test_click_by_name_exact(mock_get, mock_ext, mock_core):
    mock_get.return_value = [
        {"x": 0, "y": 0, "w": 10, "h": 10, "name": "Cancel"},
        {"x": 50, "y": 0, "w": 20, "h": 10, "name": "Submit"},
    ]
    assert labels.click_by_name(mock_core, "submit") is True
    # Clicked the centre of the Submit element (60, 5).
    assert mock_ext.call_args.args[:3] == ("Click", 60, 5)


@patch.object(labels, "_ext")
@patch.object(labels, "get_clickables")
def test_click_by_name_fuzzy(mock_get, mock_ext, mock_core):
    mock_get.return_value = [{"x": 0, "y": 0, "w": 10, "h": 10, "name": "Settings"}]
    assert labels.click_by_name(mock_core, "setings") is True
    assert mock_ext.called


@patch.object(labels, "get_clickables", return_value=[])
def test_click_by_name_no_match(mock_get, mock_core):
    assert labels.click_by_name(mock_core, "submit") is False


@patch.object(labels, "click_by_name", return_value=True)
def test_handle_click_by_name(mock_cbn, mock_core):
    assert labels.handle("click the submit button", mock_core) is True
    assert mock_cbn.call_args.args[1] == "submit button"


@patch.object(labels, "_show", return_value=True)
def test_handle_trigger_shows_labels(mock_show, mock_core):
    assert labels.handle("show buttons", mock_core) is True
    assert mock_show.called


def test_handle_unrelated_returns_none(mock_core):
    assert labels.handle("open files", mock_core) is None
