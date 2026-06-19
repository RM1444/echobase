"""Tests for the personal text snippets plugin."""

import pytest
from EchoBase.plugins import snippets


def test_non_snippet_returns_none(mock_core):
    assert snippets.handle("open files", mock_core) is None


@pytest.mark.parametrize(
    ["cmd", "key", "value"],
    [
        ("type my email", "snippet_email", "a@b.com"),
        ("type my phone", "snippet_phone", "0712345678"),
        ("insert my name", "snippet_name", "Razvan"),
        ("enter my address", "snippet_address", "1 Main St"),
    ],
)
def test_type_snippet(cmd, key, value, mock_core):
    mock_core.config = {key: value}
    mock_core.type_text.return_value = True
    assert snippets.handle(cmd, mock_core) is True
    assert mock_core.type_text.call_args.args[0] == value


def test_unset_snippet_warns(mock_core):
    mock_core.config = {"snippet_email": ""}
    assert snippets.handle("type my email", mock_core) is True
    assert not mock_core.type_text.called
    assert mock_core.speak.called


def test_no_focus(mock_core):
    mock_core.config = {"snippet_email": "a@b.com"}
    mock_core.type_text.return_value = False
    assert snippets.handle("type my email", mock_core) is True
    assert "No text field" in mock_core.speak.call_args.args[0]
