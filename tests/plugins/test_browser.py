"""Tests for the (browser-agnostic) browser plugin module."""

from unittest.mock import patch

import pytest
from EchoBase.plugins import browser

# --- Pure parsing helpers (browser-independent) ------------------------------


@pytest.mark.parametrize(
    ["input_cmd", "expected"],
    [
        ("zero two", "02"),
        ("one", "1"),
        ("nine", "9"),
        ("zero one two three", "0123"),
        ("oh five", "05"),
        ("won tu", "12"),
        ("tree for", "34"),
        ("eight ate", "88"),
        ("sex seven", "67"),
        ("nein", "9"),
        ("0 1 2", "012"),
        ("test zero test", "0"),
        ("no numbers here", ""),
    ],
)
def test_parse_hint_numbers(input_cmd, expected):
    assert browser.parse_hint_numbers(input_cmd) == expected


@pytest.mark.parametrize(
    ["input_cmd", "expected"],
    [
        ("02", True),
        ("92", True),
        ("o2", True),
        ("zero two", False),
        ("one", True),
        ("nine", True),
        ("zero one two", False),
        ("123456789", False),
        ("this is a sentence", False),
        ("open youtube", False),
        ("back", False),
        ("", True),
    ],
)
def test_looks_like_hint(input_cmd, expected):
    assert browser.looks_like_hint(input_cmd) == expected


@pytest.mark.parametrize(
    ["input_cmd", "expected"],
    [
        ("zero two", "02"),
        ("ninety three", "93"),
        ("twenty one", "21"),
        ("fifty", "5"),
        ("ten", "10"),
        ("one two three", "123"),
        ("5", "5"),
        ("92", "92"),
        ("hello world", ""),
    ],
)
def test_parse_hint_number(input_cmd, expected):
    assert browser.parse_hint_number(input_cmd) == expected


@pytest.mark.parametrize(
    ["spoken_url", "expected"],
    [
        ("claude dot ai", "https://claude.ai"),
        ("github dot com", "https://github.com"),
        ("example dot com slash page", "https://example.com/page"),
        ("test dash site dot com", "https://test-site.com"),
        ("site dot co dot uk", "https://site.co.uk"),
        ("CLAUDE DOT AI", "https://claude.ai"),
        ("https://example.com", "https://example.com"),
    ],
)
def test_parse_spoken_url(spoken_url, expected):
    assert browser.parse_spoken_url(spoken_url) == expected


# --- Command handling (universal: keys, scroll, labels) ----------------------


@pytest.mark.parametrize("command", ["numbers", "hints", "links", "clicks"])
@patch.object(browser, "labels")
def test_hint_commands_show_labels(mock_labels, command, mock_core):
    assert browser.handle_browser_command(command, mock_core) is True
    assert mock_labels.show.called
    assert mock_labels.show.call_args.args[0] == mock_core


@pytest.mark.parametrize(
    ["command", "combo"],
    [
        ("back", "alt+left"),
        ("go back", "alt+left"),
        ("forward", "alt+right"),
        ("reload", "ctrl+r"),
        ("refresh", "ctrl+r"),
        ("new tab", "ctrl+t"),
        ("close tab", "ctrl+w"),
        ("next tab", "ctrl+tab"),
        ("last tab", "ctrl+shift+tab"),
        ("reopen tab", "ctrl+shift+t"),
        ("top", "ctrl+home"),
        ("bottom", "ctrl+end"),
    ],
)
@patch.object(browser, "_key")
def test_key_commands(mock_key, command, combo, mock_core):
    assert browser.handle_browser_command(command, mock_core) is True
    assert mock_key.call_args.args[0] == combo


@pytest.mark.parametrize(
    ["command", "expected_tab"],
    [("tab one", "ctrl+1"), ("tab five", "ctrl+5"), ("tab 3", "ctrl+3")],
)
@patch.object(browser, "_key")
def test_tab_switch(mock_key, command, expected_tab, mock_core):
    assert browser.handle_browser_command(command, mock_core) is True
    assert mock_key.call_args.args[0] == expected_tab


@pytest.mark.parametrize(
    ["command", "direction"],
    [("scroll down", "down"), ("down", "down"), ("scroll up", "up"), ("up", "up")],
)
@patch.object(browser, "_scroll")
def test_scroll_commands(mock_scroll, command, direction, mock_core):
    assert browser.handle_browser_command(command, mock_core) is True
    assert mock_scroll.call_args.args[0] == direction


@pytest.mark.parametrize("command", ["escape", "cancel", "nevermind", "stop loading"])
@patch.object(browser, "_press")
def test_escape_and_stop(mock_press, command, mock_core):
    assert browser.handle_browser_command(command, mock_core) is True
    assert mock_press.call_args.args[0] == "escape"


@patch.object(browser, "_key")
def test_find_text(mock_key, mock_core):
    assert browser.handle_browser_command("find hello", mock_core) is True
    assert mock_key.call_args_list[0].args[0] == "ctrl+f"
    assert mock_core.type_text.call_args.args[0] == "hello"


@pytest.mark.parametrize(
    ["command", "combo"],
    [("find next", "ctrl+g"), ("find previous", "ctrl+shift+g")],
)
@patch.object(browser, "_key")
def test_find_navigation(mock_key, command, combo, mock_core):
    assert browser.handle_browser_command(command, mock_core) is True
    assert mock_key.call_args.args[0] == combo


@pytest.mark.parametrize(
    ["command", "url"],
    [
        ["go to youtube", "https://youtube.com"],
        ["go to github", "https://github.com"],
        ["go to claude dot ai", "https://claude.ai"],
    ],
)
@patch.object(browser, "_navigate")
def test_go_to(mock_navigate, command, url, mock_core):
    assert browser.handle_browser_command(command, mock_core) is True
    assert mock_navigate.call_args.args[0] == url
    assert mock_core.speak.called


@patch.object(browser, "_navigate")
def test_go_to_unknown_searches(mock_navigate, mock_core):
    assert browser.handle_browser_command("go to weather today", mock_core) is True
    assert "duckduckgo.com" in mock_navigate.call_args.args[0]


@patch.object(browser, "_navigate")
def test_search(mock_navigate, mock_core):
    assert browser.handle_browser_command("search python tutorial", mock_core) is True
    assert mock_navigate.call_args.args[0] == (
        "https://duckduckgo.com/?q=python+tutorial"
    )


@patch.object(browser, "_key")
def test_bookmark_this(mock_key, mock_core):
    assert browser.handle_browser_command("bookmark this", mock_core) is True
    assert mock_key.call_args.args[0] == "ctrl+d"


@patch.object(browser, "_navigate")
def test_open_unknown_returns_none(mock_navigate, mock_core):
    # Bare "open X" is left for the apps plugin.
    assert browser.handle_browser_command("open myapp", mock_core) is None
    assert not mock_navigate.called


def test_unknown_command(mock_core):
    assert browser.handle_browser_command("unknown command", mock_core) is None


def test_setup(mock_core):
    browser.setup(mock_core)
    assert browser.core == mock_core


# --- handle() entry + browser_mode -------------------------------------------


@pytest.mark.parametrize(
    "command", ["browser", "browser mode", "open browser", "launch browser"]
)
@patch("time.sleep")
@patch.object(browser, "launch_browser")
@patch.object(browser, "browser_mode")
def test_handle_enters_browser_mode(
    mock_browser_mode, mock_launch, mock_sleep, command, mock_core
):
    assert browser.handle(command, mock_core) is True
    assert mock_launch.called
    assert mock_browser_mode.called


@patch.object(browser, "handle_browser_command")
@patch.object(browser, "browser_mode")
def test_handle_single_command_enters_mode(
    mock_browser_mode, mock_handle_cmd, mock_core
):
    mock_handle_cmd.return_value = True
    assert browser.handle("back", mock_core) is True
    assert mock_browser_mode.called


@patch.object(browser, "handle_browser_command")
def test_handle_unmatched(mock_handle_cmd, mock_core):
    mock_handle_cmd.return_value = None
    assert browser.handle("unrelated command", mock_core) is None


@pytest.mark.parametrize(
    "exit_command",
    ["exit browser", "leave browser", "stop browser", "quit browser", "close browser"],
)
@patch.object(browser, "handle_browser_command")
def test_browser_mode_exit(mock_handle_cmd, exit_command, mock_core_factory, capsys):
    mock_core = mock_core_factory(
        wait_for_speech_values=[b"audio"], transcribe_values=[exit_command]
    )
    browser.browser_mode(mock_core)
    assert "leaving browser mode" in capsys.readouterr().out


@patch.object(browser, "handle_browser_command")
def test_browser_mode_grid_handoff(mock_handle_cmd, mock_core_factory, capsys):
    mock_core = mock_core_factory(
        wait_for_speech_values=[b"audio"], transcribe_values=["grid"]
    )
    browser.browser_mode(mock_core)
    assert mock_core.route_command.called
    assert "leaving browser mode for grid" in capsys.readouterr().out
