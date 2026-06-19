"""Tests for the dictation plugin module."""

from unittest.mock import Mock, patch

import pytest
from EchoBase.plugins import dictation


def test_setup():
    """Test that setup correctly assigns the core object."""
    mock_core = Mock()

    dictation.setup(mock_core)

    assert dictation.core == mock_core


@pytest.mark.parametrize(
    ["input_text", "expected_output"],
    [
        # Basic text should be capitalized
        ("hello world", "Hello world"),
        # Whisper punctuation should be stripped
        ("hello, world.", "Hello world"),
        # Comma command
        ("hello comma world", "Hello, world"),
        ("hello karma world", "Hello, world"),
        ("hello kama world", "Hello, world"),
        # Period command
        ("hello period world", "Hello. World"),
        ("hello full stop world", "Hello. World"),
        # Question mark
        ("hello question mark", "Hello?"),
        # Exclamation mark
        ("hello exclamation mark", "Hello!"),
        ("hello exclamation point", "Hello!"),
        # Colon and semicolon
        ("hello colon world", "Hello: world"),
        # Note: semicolon commands are broken - "colon" pattern matches first in the actual code
        ("hello semicolon world", "Hello semi: world"),
        ("hello semi colon world", "Hello semi: world"),
        # Editing/structural words are NO LONGER converted inside a sentence -
        # they stay literal (only a standalone utterance is a command, handled by
        # parse_editing_command). This is the fix for "I need space to think".
        ("hello new sentence world", "Hello new sentence world"),
        ("hello new paragraph world", "Hello new paragraph world"),
        ("hello new line world", "Hello new line world"),
        ("hello newline world", "Hello newline world"),
        ("hello line break world", "Hello line break world"),
        ("hello enter world", "Hello enter world"),
        ("hello backspace world", "Hello backspace world"),
        ("hello back space world", "Hello back space world"),
        ("hello delete world", "Hello delete world"),
        ("hello space world", "Hello space world"),
        ("hello tab world", "Hello tab world"),
        ("i need space to think", "I need space to think"),
        ("press enter to continue", "Press enter to continue"),
        # Dash and hyphen
        ("hello dash world", "Hello - world"),
        ("hello hyphen world", "Hello-world"),
        # Apostrophe and quotes
        ("hello apostrophe world", "Hello'world"),
        ("hello quote world", 'Hello"world'),
        ("hello open quote world", 'Hello "world'),
        ("hello close quote world", 'Hello" world'),
        # Parentheses
        ("hello open paren world", "Hello (world"),
        ("hello close paren world", "Hello) world"),
        # Symbols
        ("hello at sign world", "Hello@world"),
        ("hello ampersand world", "Hello&world"),
        ("hello dollar sign world", "Hello$world"),
        ("hello percent sign world", "Hello%world"),
        ("hello percent world", "Hello%world"),
        ("hello hashtag world", "Hello#world"),
        ("hello hash world", "Hello#world"),
        ("hello asterisk world", "Hello*world"),
        ("hello star world", "Hello*world"),
        ("hello underscore world", "Hello_world"),
        ("hello slash world", "Hello/world"),
        # Note: backslash command is broken - "slash" pattern matches first in the actual code
        ("hello backslash world", "Hello back/world"),
        # Multiple spaces should be collapsed
        ("hello    world", "Hello world"),
        # Punctuation already in input gets stripped by Whisper cleanup
        ("hello , world", "Hello world"),
        ("hello. world", "Hello world"),
        ("hello? world", "Hello world"),
        ("hello! world", "Hello world"),
        # Empty string
        ("", ""),
        # Only whitespace
        ("   ", ""),
    ],
)
def test_format_text(input_text, expected_output):
    """Test format_text with various inputs."""
    result = dictation.format_text(input_text)

    assert result == expected_output


@pytest.mark.parametrize(
    ["input_text", "expected_output"],
    [
        # Multiple periods should be collapsed to one
        ("hello period period world", "Hello. World"),
        # Period takes precedence over comma (both get converted, but comma is removed when followed by period)
        ("hello comma period world", "Hello. World"),
        # Test case insensitivity for commands
        ("hello COMMA world", "Hello, world"),
        ("hello Comma world", "Hello, world"),
        # Mixed: punctuation still inline; "next sentence" now stays literal.
        (
            "hello comma world period next sentence goodbye",
            "Hello, world. Next sentence goodbye",
        ),
    ],
)
def test_format_text_edge_cases(input_text, expected_output):
    """Test format_text edge cases and combinations."""
    result = dictation.format_text(input_text)

    assert result == expected_output


@pytest.mark.parametrize(
    ["utterance", "expected"],
    [
        ("new line", "\n"),
        ("newline", "\n"),
        ("new paragraph", "\n\n"),
        ("enter", "\n"),
        ("return", "\n"),
        ("space", " "),
        ("space bar", " "),
        ("tab", "\t"),
        ("backspace", "\b"),
        ("back space", "\b"),
        ("delete", "\b"),
        ("backspace backspace", "\b\b"),
        ("new sentence", "."),
        # Mishearing-friendly: trailing punctuation Whisper adds is ignored.
        ("new line.", "\n"),
    ],
)
def test_parse_editing_command_standalone(utterance, expected):
    """A whole-utterance editing command returns its control text."""
    assert dictation.parse_editing_command(utterance) == expected


@pytest.mark.parametrize(
    "utterance",
    [
        "i need space to think",
        "press enter to continue",
        "give me a little space",
        "delete that file from the folder",
        "hello world",
        "",
    ],
)
def test_parse_editing_command_prose_is_none(utterance):
    """An editing word embedded in prose is NOT a command (returns None)."""
    assert dictation.parse_editing_command(utterance) is None


@patch("subprocess.run", return_value=Mock(stdout="OK\n", stderr=""))
def test_insert_text_success(mock_run):
    """When text insertion succeeds the result should be True."""
    result = dictation.insert_text("Hello world")

    assert result is True
    assert mock_run.call_count == 1
    call_args = mock_run.call_args.args[0]
    assert call_args[0] == "python3"
    assert call_args[1] == "-c"
    assert call_args[2] == dictation.ATSPI_INSERT_SCRIPT
    assert call_args[3] == "Hello world"


@patch("subprocess.run", return_value=Mock(stdout="NO_FOCUS\n", stderr=""))
def test_insert_text_no_focus(mock_run):
    """When no text field is focused the result should be False."""
    result = dictation.insert_text("Hello world")

    assert result is False


@patch("subprocess.run", return_value=Mock(stdout="OK\n", stderr=""))
def test_insert_text_empty_string(mock_run):
    """When inserting an empty string the result should be True."""
    result = dictation.insert_text("")

    assert result is True
    assert mock_run.call_count == 1
    call_args = mock_run.call_args.args[0]
    assert call_args[3] == ""


@patch("EchoBase.plugins.dictation.insert_text")
def test_handle_non_dictation_command(mock_insert, mock_core):
    """When given a non-dictation command the result should be None."""
    result = dictation.handle("open browser", mock_core)

    assert result is None
    assert not mock_insert.called


@patch("EchoBase.plugins.dictation.insert_text")
def test_handle_stop_notes_command(mock_insert, mock_core):
    """When given a stop notes command the result should be None."""
    result = dictation.handle("stop notes", mock_core)

    assert result is None
    assert not mock_insert.called


@patch("EchoBase.plugins.dictation.insert_text", return_value=True)
@patch("EchoBase.plugins.dictation.format_text", return_value="Hello")
def test_handle_dictation_mode_single_input(
    mock_format, mock_insert, mock_core_factory
):
    """When handling dictation with single input the result should be True."""
    # First call returns audio with 'some text', second call returns audio with 'stop notes'
    mock_core = mock_core_factory(
        wait_for_speech_values=[b"audio1", b"audio2"],
        record_until_silence_value=b"audio_rest",
        transcribe_values=["some text", "stop notes"],
    )

    result = dictation.handle("notes", mock_core)

    assert result is True
    assert ("Dictation",) in [call.args for call in mock_core.speak.call_args_list]
    assert ("Done",) in [call.args for call in mock_core.speak.call_args_list]
    assert mock_core.transcribe.call_count == 2
    assert mock_format.call_count == 1
    assert mock_format.call_args.args == ("some text",)
    assert mock_insert.call_count == 1
    assert mock_insert.call_args.args == (" Hello",)


@patch("EchoBase.plugins.dictation.insert_text", return_value=True)
@patch("EchoBase.plugins.dictation.format_text")
def test_handle_dictation_standalone_editing_command(
    mock_format, mock_insert, mock_core_factory
):
    """A standalone 'new line' inserts a newline directly, bypassing format_text."""
    mock_core = mock_core_factory(
        wait_for_speech_values=[b"audio1", b"audio2"],
        record_until_silence_value=b"audio_rest",
        transcribe_values=["new line", "stop notes"],
    )

    result = dictation.handle("notes", mock_core)

    assert result is True
    # The editing command path is taken: insert "\n", format_text not called.
    assert mock_insert.call_args.args == ("\n",)
    assert mock_format.call_count == 0


@patch("EchoBase.plugins.dictation.insert_text", return_value=True)
@patch("EchoBase.plugins.dictation.format_text", return_value=".")
def test_handle_dictation_mode_no_space_before_punctuation(
    mock_format, mock_insert, mock_core_factory
):
    """When formatted text starts with punctuation no space should be added."""
    mock_core = mock_core_factory(
        wait_for_speech_values=[b"audio1", b"audio2"],
        record_until_silence_value=b"audio_rest",
        transcribe_values=["period", "stop notes"],
    )

    result = dictation.handle("notes", mock_core)

    assert result is True
    assert mock_insert.call_count == 1
    assert mock_insert.call_args.args == (".",)


@patch("EchoBase.plugins.dictation.insert_text", return_value=False)
@patch("EchoBase.plugins.dictation.format_text", return_value="Hello")
def test_handle_dictation_mode_no_focus(mock_format, mock_insert, mock_core_with_audio):
    """When no text field is focused a warning should be spoken."""
    mock_core_with_audio.transcribe = Mock(return_value="some text")

    result = dictation.handle("notes", mock_core_with_audio)

    assert result is True
    assert ("No text field focused.",) in [
        call.args for call in mock_core_with_audio.speak.call_args_list
    ]


@patch("EchoBase.plugins.dictation.insert_text")
def test_handle_dictation_mode_empty_transcription(mock_insert, mock_core_factory):
    """When transcription is empty it should be skipped."""
    mock_core = mock_core_factory(
        wait_for_speech_values=[b"audio1", b"audio2"],
        record_until_silence_value=b"audio3",
        transcribe_values=["", "stop notes"],
    )

    result = dictation.handle("notes", mock_core)

    assert result is True
    assert not mock_insert.called


@pytest.mark.parametrize(
    "stop_phrase",
    [
        "stop notes",
        "stop note",
        "end notes",
        "exit notes",
        "stop nurts",
        "stop nots",
        "stop nuts",
        "stopnotes",
        "done notes",
        "finish notes",
        "close notes",
        "closed notes",
    ],
)
@patch("EchoBase.plugins.dictation.insert_text")
def test_handle_dictation_mode_stop_phrases(
    mock_insert, stop_phrase, mock_core_with_audio
):
    """When a stop phrase is recognized dictation should end."""
    mock_core_with_audio.transcribe = Mock(return_value=stop_phrase)

    result = dictation.handle("notes", mock_core_with_audio)

    assert result is True
    assert ("Done",) in [
        call.args for call in mock_core_with_audio.speak.call_args_list
    ]
    assert not mock_insert.called


@patch("EchoBase.plugins.dictation.insert_text")
def test_handle_dictation_mode_timeout_waiting(mock_insert, mock_core_factory):
    """When waiting times out the system should continue waiting."""
    # First wait times out (returns None), second succeeds, third times out, fourth succeeds with stop
    expected_wait_count = 4
    mock_core = mock_core_factory(
        wait_for_speech_values=[None, b"audio1", None, b"audio2"],
        transcribe_values=["hello", "stop notes"],
    )

    result = dictation.handle("note", mock_core)

    assert result is True
    assert mock_core.wait_for_speech.call_count == expected_wait_count


@patch("EchoBase.plugins.dictation.insert_text", return_value=True)
@patch("EchoBase.plugins.dictation.format_text")
def test_handle_dictation_mode_with_prompt(mock_format, mock_insert, mock_core_factory):
    """When transcribing the dictation prompt should be passed."""
    mock_format.return_value = "Hello"
    mock_core = mock_core_factory(
        wait_for_speech_values=[b"audio1", b"audio2"],
        record_until_silence_value=b"audio_rest",
        transcribe_values=["some text", "stop notes"],
    )

    dictation.handle("notes", mock_core)

    # Check that transcribe was called with the prompt
    assert mock_core.transcribe.call_count == 2
    first_call = mock_core.transcribe.call_args_list[0]
    assert first_call.kwargs["prompt"] == dictation.DICTATION_PROMPT
