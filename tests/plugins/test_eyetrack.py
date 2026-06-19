"""Tests for the eyetrack (head tracking) plugin module."""

import importlib
import json
import time
from unittest.mock import Mock, patch

import pytest

eyetrack_plugin = importlib.import_module("EchoBase.plugins.00_eyetrack")


@pytest.fixture(autouse=True)
def reset_eyetrack_state():
    """Reset eyetrack plugin global state before and after each test."""
    # Reset to clean state before test
    eyetrack_plugin.tracking_active = False
    eyetrack_plugin.frozen = False
    eyetrack_plugin.core = None  # avoid a Mock core leaking in from test_setup
    eyetrack_plugin.stop_event.clear()
    # Multi-monitor state must not leak between tests.
    eyetrack_plugin.monitors = []
    eyetrack_plugin.active_monitor = 0
    eyetrack_plugin.monitor_mode = "active"

    yield

    # Cleanup after test
    eyetrack_plugin.tracking_active = False
    eyetrack_plugin.frozen = False
    eyetrack_plugin.stop_event.set()
    if eyetrack_plugin.tracking_thread is not None:
        time.sleep(0.1)  # Give thread time to stop


def test_setup(mock_core):
    """When setup is called with a core object then it stores the reference."""
    eyetrack_plugin.setup(mock_core)

    assert eyetrack_plugin.core is mock_core


# --- Snap-to-element ("hold onto a button") ---------------------------------


def test_snap_center_no_targets_passthrough():
    eyetrack_plugin.snap_enabled = True
    eyetrack_plugin._snap_targets = []
    assert eyetrack_plugin._snap_center(5.0, 5.0) == (5.0, 5.0)


def test_snap_center_disabled_passthrough():
    eyetrack_plugin.snap_enabled = False
    eyetrack_plugin._snap_targets = [{"x": 0, "y": 0, "w": 10, "h": 10}]
    assert eyetrack_plugin._snap_center(3.0, 3.0) == (3.0, 3.0)


def test_snap_center_inside_pulls_to_center():
    eyetrack_plugin.snap_enabled = True
    eyetrack_plugin._snap_targets = [{"x": 100, "y": 100, "w": 40, "h": 40}]
    # Point inside the element, off-centre -> pulled toward centre (120, 120).
    x, y = eyetrack_plugin._snap_center(105.0, 105.0)
    assert 105.0 < x <= 120.0
    assert 105.0 < y <= 120.0


def test_snap_center_far_element_ignored():
    eyetrack_plugin.snap_enabled = True
    eyetrack_plugin._snap_targets = [{"x": 1000, "y": 1000, "w": 20, "h": 20}]
    # Target far outside the snap radius -> unchanged.
    assert eyetrack_plugin._snap_center(10.0, 10.0) == (10.0, 10.0)


@patch("subprocess.run", return_value=Mock(returncode=0, stdout="", stderr=""))
def test_host_run(mock_subprocess_run):
    """When host_run is called then it executes subprocess with capture_output and text."""
    cmd = ["test", "command"]

    result = eyetrack_plugin.host_run(cmd)

    assert mock_subprocess_run.call_args.args[0] == cmd
    assert mock_subprocess_run.call_args.kwargs["capture_output"] is True
    assert mock_subprocess_run.call_args.kwargs["text"] is True
    assert result.returncode == 0


@pytest.mark.parametrize(
    ["method", "args", "expected_returncode", "expected_result"],
    [
        ("MoveTo", [100, 200], 0, True),
        ("Click", [100, 200], 0, True),
        ("DoubleClick", [100, 200], 0, True),
        ("RightClick", [100, 200], 0, True),
        ("MoveTo", [100, 200], 1, False),
    ],
)
@patch.object(eyetrack_plugin, "host_run")
def test_dbus_call(mock_host_run, method, args, expected_returncode, expected_result):
    """When dbus_call is invoked then it constructs gdbus command and returns success status."""
    mock_host_run.return_value = Mock(returncode=expected_returncode)

    result = eyetrack_plugin.dbus_call(method, *args)

    assert result == expected_result
    call_args = mock_host_run.call_args.args[0]
    assert call_args[0] == "gdbus"
    assert call_args[1] == "call"
    assert call_args[2] == "--session"
    assert call_args[3] == "--dest"
    assert call_args[4] == "org.gnome.Shell"
    assert call_args[5] == "--object-path"
    assert call_args[6] == "/org/EchoBase/Grid"
    assert call_args[7] == "--method"
    assert call_args[8] == f"org.EchoBase.Grid.{method}"
    assert call_args[9:] == [str(a) for a in args]


@pytest.mark.parametrize(
    ["stdout", "expected_size"],
    [
        ("(1920, 1080)\n", (1920, 1080)),
        ("(2560, 1440)\n", (2560, 1440)),
        ("(3840, 2160)\n", (3840, 2160)),
        ("invalid output", (1920, 1080)),
        ("", (1920, 1080)),
    ],
)
@patch.object(eyetrack_plugin, "host_run")
def test_get_screen_size(mock_host_run, stdout, expected_size):
    """When get_screen_size is called then it parses screen dimensions from gdbus output."""
    mock_host_run.return_value = Mock(returncode=0, stdout=stdout)

    result = eyetrack_plugin.get_screen_size()

    assert result == expected_size
    call_args = mock_host_run.call_args.args[0]
    assert call_args[0] == "gdbus"
    assert call_args[4] == "org.gnome.Shell"
    assert call_args[6] == "/org/EchoBase/Grid"
    assert call_args[8] == "org.EchoBase.Grid.GetScreenSize"


@patch.object(eyetrack_plugin, "host_run", return_value=Mock(returncode=1, stdout=""))
def test_get_screen_size_with_failure(mock_host_run):
    """When get_screen_size fails then it returns default dimensions."""
    result = eyetrack_plugin.get_screen_size()

    assert result == (1920, 1080)


def test_start_tracking_when_already_active():
    """When start_tracking is called while tracking is active then it returns failure."""
    eyetrack_plugin.tracking_active = True

    success, msg = eyetrack_plugin.start_tracking()

    assert success is False
    assert msg == "Already tracking"


@patch.object(eyetrack_plugin, "refresh_monitors")
@patch.object(eyetrack_plugin, "run_tracking")
def test_start_tracking_when_inactive(mock_run_tracking, mock_refresh):
    """When start_tracking is called while inactive then it starts tracking thread."""
    eyetrack_plugin.tracking_active = False
    eyetrack_plugin.frozen = True

    success, msg = eyetrack_plugin.start_tracking()

    assert success is True
    assert msg == "Tracking"
    assert eyetrack_plugin.frozen is False
    assert eyetrack_plugin.tracking_active is True
    assert eyetrack_plugin.stop_event.is_set() is False
    assert eyetrack_plugin.tracking_thread is not None
    assert eyetrack_plugin.tracking_thread.daemon is True


def test_stop_tracking():
    """When stop_tracking is called then it signals thread to stop and sets tracking_active to False."""
    eyetrack_plugin.tracking_active = True
    eyetrack_plugin.stop_event.clear()

    success, msg = eyetrack_plugin.stop_tracking()

    assert success is True
    assert msg == "Stopped"
    assert eyetrack_plugin.tracking_active is False
    assert eyetrack_plugin.stop_event.is_set() is True


def test_recalibrate_when_tracking():
    """When recalibrate is called during tracking then it re-centers in place by
    setting the _recalibrate flag (no thread restart)."""
    eyetrack_plugin.tracking_active = True
    eyetrack_plugin._recalibrate = False

    success, msg = eyetrack_plugin.recalibrate()

    assert success is True
    assert msg == "Recalibrating"
    assert eyetrack_plugin._recalibrate is True


def test_recalibrate_when_not_tracking():
    """When recalibrate is called while not tracking then it returns failure."""
    eyetrack_plugin.tracking_active = False

    success, msg = eyetrack_plugin.recalibrate()

    assert success is False
    assert msg == "Not tracking"


@pytest.mark.parametrize(
    ["command"],
    [
        ["start tracking"],
        ["begin tracking"],
        ["enable tracking"],
    ],
)
@patch.object(eyetrack_plugin, "listen_for_tracking_commands")
@patch.object(eyetrack_plugin, "start_tracking", return_value=(True, "Tracking"))
def test_handle_start_tracking_commands(mock_start, mock_listen, command, mock_core):
    """When handle receives a start tracking command then it starts tracking and listens."""
    result = eyetrack_plugin.handle(command, mock_core)

    assert result is True
    assert mock_start.called
    assert mock_core.speak.call_args.args[0] == "Tracking"
    assert mock_listen.call_args.args[0] == mock_core


@pytest.mark.parametrize(
    ["command"],
    [
        ["stop tracking"],
        ["end tracking"],
        ["close tracking"],
        ["quit tracking"],
        ["disable tracking"],
        ["tracking off"],
        ["stop track"],
    ],
)
@patch.object(eyetrack_plugin, "stop_tracking", return_value=(True, "Stopped"))
def test_handle_stop_tracking_commands(mock_stop, command, mock_core):
    """When handle receives a stop tracking command then it stops tracking."""
    result = eyetrack_plugin.handle(command, mock_core)

    assert result is True
    assert mock_stop.called
    assert mock_core.speak.call_args.args[0] == "Stopped"


@pytest.mark.parametrize(
    ["command"],
    [
        ["recalibrate"],
        ["calibrate"],
    ],
)
@patch.object(eyetrack_plugin, "recalibrate", return_value=(True, "Recalibrating"))
def test_handle_recalibrate_commands(mock_recalibrate, command, mock_core):
    """When handle receives a recalibrate command then it recalibrates."""
    result = eyetrack_plugin.handle(command, mock_core)

    assert result is True
    assert mock_recalibrate.called
    assert mock_core.speak.call_args.args[0] == "Recalibrating"


def test_handle_unrecognized_command(mock_core):
    """When handle receives an unrecognized command then it returns None."""
    result = eyetrack_plugin.handle("unrelated command", mock_core)

    assert result is None
    assert not mock_core.speak.called


@patch.object(
    eyetrack_plugin, "start_tracking", return_value=(False, "Already tracking")
)
def test_handle_start_tracking_when_already_active(mock_start, mock_core):
    """When handle receives start tracking while already active then it does not call listen."""
    with patch.object(eyetrack_plugin, "listen_for_tracking_commands") as mock_listen:
        result = eyetrack_plugin.handle("start tracking", mock_core)

        assert result is True
        assert mock_start.called
        assert mock_core.speak.call_args.args[0] == "Already tracking"
        assert not mock_listen.called


def test_one_euro_filter_first_call_returns_input():
    """When filter is called first time then it returns input value unchanged."""
    filter_obj = eyetrack_plugin.OneEuroFilter()

    result = filter_obj(10.0)

    assert result == 10.0
    assert filter_obj.x_prev == 10.0


def test_one_euro_filter_smoothing_with_constant_input():
    """When filter receives constant input then it smooths toward that value."""
    filter_obj = eyetrack_plugin.OneEuroFilter()

    filter_obj(0.0)
    result = filter_obj(10.0)

    assert result < 10.0
    assert result > 0.0


def test_one_euro_filter_multiple_calls_converge():
    """When filter receives same value repeatedly then output converges to input."""
    filter_obj = eyetrack_plugin.OneEuroFilter()

    filter_obj(0.0)
    for _ in range(100):
        result = filter_obj(10.0)

    assert abs(result - 10.0) < 0.1


def test_one_euro_filter_alpha_calculation():
    """When _alpha is called then it calculates exponential smoothing factor."""
    filter_obj = eyetrack_plugin.OneEuroFilter(freq=30.0)

    alpha = filter_obj._alpha(1.0)

    assert 0.0 < alpha < 1.0


def test_one_euro_filter_derivative_tracking():
    """When filter processes values then it tracks derivative for adaptive cutoff."""
    filter_obj = eyetrack_plugin.OneEuroFilter()

    filter_obj(0.0)
    filter_obj(1.0)

    assert filter_obj.dx_prev != 0.0


def test_one_euro_filter_custom_parameters():
    """When filter is created with custom parameters then they are stored."""
    filter_obj = eyetrack_plugin.OneEuroFilter(
        freq=60.0, min_cutoff=2.0, beta=0.01, d_cutoff=2.0
    )

    assert filter_obj.freq == 60.0
    assert filter_obj.min_cutoff == 2.0
    assert filter_obj.beta == 0.01
    assert filter_obj.d_cutoff == 2.0


@patch.object(eyetrack_plugin, "get_screen_size", return_value=(1920, 1080))
@patch.object(eyetrack_plugin, "dbus_call", return_value=True)
def test_listen_for_tracking_commands_stops_on_stop_command(
    mock_dbus, mock_screen_size, mock_core
):
    """When listen_for_tracking_commands receives stop then it exits loop."""
    eyetrack_plugin.tracking_active = True
    mock_core.wait_for_speech.return_value = b"audio"
    mock_core.record_until_silence.return_value = b"more_audio"
    mock_core.transcribe.return_value = "stop tracking"

    eyetrack_plugin.listen_for_tracking_commands(mock_core)

    assert mock_core.speak.call_args.args[0] == "Stopped"
    assert eyetrack_plugin.tracking_active is False


@patch.object(eyetrack_plugin, "get_screen_size", return_value=(1920, 1080))
@patch.object(eyetrack_plugin, "dbus_call", return_value=True)
def test_listen_for_tracking_commands_freeze(mock_dbus, mock_screen_size, mock_core):
    """When listen_for_tracking_commands receives freeze then it sets frozen flag."""
    eyetrack_plugin.tracking_active = True
    eyetrack_plugin.frozen = False
    eyetrack_plugin.cursor_x = 100
    eyetrack_plugin.cursor_y = 200

    mock_core.wait_for_speech.side_effect = [b"audio1", b"audio2"]
    mock_core.record_until_silence.return_value = b"more_audio"
    mock_core.transcribe.side_effect = ["freeze", "stop"]

    eyetrack_plugin.listen_for_tracking_commands(mock_core)

    assert eyetrack_plugin.frozen is False


@patch.object(eyetrack_plugin, "get_screen_size", return_value=(1920, 1080))
@patch.object(eyetrack_plugin, "dbus_call", return_value=True)
def test_listen_for_tracking_commands_click(mock_dbus, mock_screen_size, mock_core):
    """When listen_for_tracking_commands receives click then it calls dbus Click."""
    eyetrack_plugin.tracking_active = True
    eyetrack_plugin.cursor_x = 100
    eyetrack_plugin.cursor_y = 200

    mock_core.wait_for_speech.side_effect = [b"audio1", b"audio2"]
    mock_core.record_until_silence.return_value = b"more_audio"
    mock_core.transcribe.side_effect = ["click", "stop"]

    eyetrack_plugin.listen_for_tracking_commands(mock_core)

    click_calls = [call for call in mock_dbus.call_args_list if call.args[0] == "Click"]
    assert len(click_calls) >= 1


@patch.object(eyetrack_plugin, "get_screen_size", return_value=(1920, 1080))
@patch.object(eyetrack_plugin, "dbus_call", return_value=True)
def test_listen_for_tracking_commands_nudge_when_frozen(
    mock_dbus, mock_screen_size, mock_core
):
    """When listen_for_tracking_commands receives nudge while frozen then it adjusts cursor."""
    eyetrack_plugin.tracking_active = True
    eyetrack_plugin.frozen = True
    eyetrack_plugin.cursor_x = 500
    eyetrack_plugin.cursor_y = 500

    mock_core.wait_for_speech.side_effect = [b"audio1", b"audio2"]
    mock_core.record_until_silence.return_value = b"more_audio"
    mock_core.transcribe.side_effect = ["nudge right", "stop"]

    eyetrack_plugin.listen_for_tracking_commands(mock_core)

    moveto_calls = [
        call for call in mock_dbus.call_args_list if call.args[0] == "MoveTo"
    ]
    assert len(moveto_calls) >= 1


@patch.object(eyetrack_plugin, "get_screen_size", return_value=(1920, 1080))
@patch.object(eyetrack_plugin, "dbus_call", return_value=True)
def test_listen_for_tracking_commands_timeout(mock_dbus, mock_screen_size, mock_core):
    """When listen_for_tracking_commands times out waiting then it continues loop."""
    eyetrack_plugin.tracking_active = True

    mock_core.wait_for_speech.side_effect = [None, b"audio"]
    mock_core.record_until_silence.return_value = b"more_audio"
    mock_core.transcribe.return_value = "stop"

    eyetrack_plugin.listen_for_tracking_commands(mock_core)

    assert mock_core.wait_for_speech.call_count == 2


@patch.object(eyetrack_plugin, "get_screen_size", return_value=(1920, 1080))
@patch.object(eyetrack_plugin, "dbus_call", return_value=True)
def test_listen_for_tracking_commands_empty_transcription(
    mock_dbus, mock_screen_size, mock_core
):
    """When listen_for_tracking_commands receives empty transcription then it continues loop."""
    eyetrack_plugin.tracking_active = True

    mock_core.wait_for_speech.side_effect = [b"audio1", b"audio2"]
    mock_core.record_until_silence.return_value = b"more_audio"
    mock_core.transcribe.side_effect = ["", "stop"]

    eyetrack_plugin.listen_for_tracking_commands(mock_core)

    assert mock_core.transcribe.call_count == 2


@patch.object(eyetrack_plugin, "get_screen_size", return_value=(1920, 1080))
@patch.object(eyetrack_plugin, "dbus_call", return_value=True)
def test_listen_for_tracking_commands_go_unfreezes(
    mock_dbus, mock_screen_size, mock_core
):
    """When listen_for_tracking_commands receives go then it unfreezes cursor."""
    eyetrack_plugin.tracking_active = True
    eyetrack_plugin.frozen = True

    mock_core.wait_for_speech.side_effect = [b"audio1", b"audio2"]
    mock_core.record_until_silence.return_value = b"more_audio"
    mock_core.transcribe.side_effect = ["go", "stop"]

    eyetrack_plugin.listen_for_tracking_commands(mock_core)

    assert eyetrack_plugin.frozen is False


@pytest.mark.parametrize(
    ["command", "expected_direction"],
    [
        ["nudge up", "up"],
        ["nudge down", "down"],
        ["nudge left", "left"],
        ["nudge right", "right"],
    ],
)
@patch.object(eyetrack_plugin, "get_screen_size", return_value=(1920, 1080))
@patch.object(eyetrack_plugin, "dbus_call", return_value=True)
def test_listen_for_tracking_commands_nudge_directions(
    mock_dbus, mock_screen_size, command, expected_direction, mock_core
):
    """When listen_for_tracking_commands receives nudge commands then it moves cursor in specified direction."""
    eyetrack_plugin.tracking_active = True
    eyetrack_plugin.frozen = True
    eyetrack_plugin.cursor_x = 500
    eyetrack_plugin.cursor_y = 500

    mock_core.wait_for_speech.side_effect = [b"audio1", b"audio2"]
    mock_core.record_until_silence.return_value = b"more_audio"
    mock_core.transcribe.side_effect = [command, "stop"]

    eyetrack_plugin.listen_for_tracking_commands(mock_core)

    moveto_calls = [
        call for call in mock_dbus.call_args_list if call.args[0] == "MoveTo"
    ]
    assert len(moveto_calls) >= 1


@patch.object(eyetrack_plugin, "get_screen_size", return_value=(1920, 1080))
@patch.object(eyetrack_plugin, "dbus_call", return_value=True)
@patch.object(eyetrack_plugin, "recalibrate", return_value=(True, "Recalibrating"))
def test_listen_for_tracking_commands_recalibrate(
    mock_recalibrate, mock_dbus, mock_screen_size, mock_core
):
    """When listen_for_tracking_commands receives recalibrate then it recalibrates."""
    eyetrack_plugin.tracking_active = True

    mock_core.wait_for_speech.side_effect = [b"audio1", b"audio2"]
    mock_core.record_until_silence.return_value = b"more_audio"
    mock_core.transcribe.side_effect = ["recalibrate", "stop"]

    eyetrack_plugin.listen_for_tracking_commands(mock_core)

    assert mock_recalibrate.called
    assert mock_core.speak.call_args_list[0].args[0] == "Recalibrating"


@patch.object(eyetrack_plugin, "get_screen_size", return_value=(1920, 1080))
@patch.object(eyetrack_plugin, "dbus_call", return_value=True)
def test_listen_for_tracking_commands_double_click(
    mock_dbus, mock_screen_size, mock_core
):
    """When listen_for_tracking_commands receives double click then it calls dbus DoubleClick."""
    eyetrack_plugin.tracking_active = True
    eyetrack_plugin.cursor_x = 100
    eyetrack_plugin.cursor_y = 200

    mock_core.wait_for_speech.side_effect = [b"audio1", b"audio2"]
    mock_core.record_until_silence.return_value = b"more_audio"
    mock_core.transcribe.side_effect = ["double click", "stop"]

    eyetrack_plugin.listen_for_tracking_commands(mock_core)

    double_click_calls = [
        call for call in mock_dbus.call_args_list if call.args[0] == "DoubleClick"
    ]
    assert len(double_click_calls) >= 1


@patch.object(eyetrack_plugin, "get_screen_size", return_value=(1920, 1080))
@patch.object(eyetrack_plugin, "dbus_call", return_value=True)
def test_listen_for_tracking_commands_right_click(
    mock_dbus, mock_screen_size, mock_core
):
    """When listen_for_tracking_commands receives right click then it calls dbus RightClick."""
    eyetrack_plugin.tracking_active = True
    eyetrack_plugin.cursor_x = 100
    eyetrack_plugin.cursor_y = 200

    mock_core.wait_for_speech.side_effect = [b"audio1", b"audio2"]
    mock_core.record_until_silence.return_value = b"more_audio"
    mock_core.transcribe.side_effect = ["right click", "stop"]

    eyetrack_plugin.listen_for_tracking_commands(mock_core)

    right_click_calls = [
        call for call in mock_dbus.call_args_list if call.args[0] == "RightClick"
    ]
    assert len(right_click_calls) >= 1


@patch.object(eyetrack_plugin, "get_screen_size", return_value=(1920, 1080))
@patch.object(eyetrack_plugin, "dbus_call", return_value=True)
def test_listen_for_tracking_commands_stream_read_exception(
    mock_dbus, mock_screen_size, mock_core
):
    """When listen_for_tracking_commands encounters stream read exception then it continues."""
    eyetrack_plugin.tracking_active = True
    mock_core.stream.read.side_effect = Exception("Stream error")

    mock_core.wait_for_speech.return_value = b"audio"
    mock_core.record_until_silence.return_value = b"more_audio"
    mock_core.transcribe.return_value = "stop"

    eyetrack_plugin.listen_for_tracking_commands(mock_core)

    assert eyetrack_plugin.tracking_active is False


@pytest.mark.parametrize(
    ["exit_command"],
    [
        ["stop tracking"],
        ["end tracking"],
        ["close tracking"],
        ["stop"],
        ["cancel"],
        ["escape"],
        ["exit"],
        ["quit"],
        ["done"],
    ],
)
@patch.object(eyetrack_plugin, "get_screen_size", return_value=(1920, 1080))
@patch.object(eyetrack_plugin, "dbus_call", return_value=True)
def test_listen_for_tracking_commands_exit_commands(
    mock_dbus, mock_screen_size, exit_command, mock_core
):
    """When listen_for_tracking_commands receives exit commands then it stops tracking."""
    eyetrack_plugin.tracking_active = True

    mock_core.wait_for_speech.return_value = b"audio"
    mock_core.record_until_silence.return_value = b"more_audio"
    mock_core.transcribe.return_value = exit_command

    eyetrack_plugin.listen_for_tracking_commands(mock_core)

    assert eyetrack_plugin.tracking_active is False
    assert mock_core.speak.call_args.args[0] == "Stopped"


@pytest.mark.parametrize(
    ["webcam_opens", "frame_count", "pose_sequence"],
    [
        # Webcam fails to open - exits immediately
        (False, 0, []),
        # Webcam opens but read fails immediately - loops but continues
        (True, 0, []),
        # Webcam opens, gets 5 frames but no face detected - continues loop
        (True, 5, []),
        # Webcam opens, gets 15 frames with a steady pose for calibration
        (True, 15, [(2.0, 1.0)]),
        # Webcam opens with a pose that drifts each frame
        (True, 50, [(i * 0.5, i * 0.5) for i in range(50)]),
        # Calibration then large positive offsets (cursor toward bottom-right)
        (True, 50, [(2.0, 1.0)] * 10 + [(12.0, 10.0)] * 40),
        # Calibration then large negative offsets (cursor toward top-left)
        (True, 50, [(2.0, 1.0)] * 10 + [(-12.0, -10.0)] * 40),
    ],
)
@patch.object(eyetrack_plugin, "get_screen_size", return_value=(1920, 1080))
@patch.object(eyetrack_plugin, "dbus_call", return_value=True)
def test_run_tracking_scenarios(
    mock_dbus,
    mock_screen_size,
    webcam_opens,
    frame_count,
    pose_sequence,
):
    """When run_tracking is called with various scenarios then it handles them appropriately."""
    mock_cap = Mock()
    mock_cap.isOpened.return_value = webcam_opens

    # Set up frame reading to return frames for frame_count iterations
    read_counter = [0]

    def read_side_effect():
        read_counter[0] += 1
        if read_counter[0] > frame_count + 20:
            # Safety: force stop after many iterations to prevent infinite loop
            eyetrack_plugin.stop_event.set()
        if read_counter[0] <= frame_count:
            return (True, Mock())
        return (False, None)

    mock_cap.read.side_effect = read_side_effect
    mock_cap.release = Mock()

    # estimate_pose yields the next (yaw, pitch) each frame, or None for "no face".
    pose_counter = [0]

    def pose_side_effect(frame, face_mesh):
        if not pose_sequence:
            return None
        idx = pose_counter[0]
        pose_counter[0] += 1
        return pose_sequence[idx] if idx < len(pose_sequence) else pose_sequence[-1]

    mock_cv2 = Mock()
    mock_cv2.VideoCapture.return_value = mock_cap
    mock_cv2.flip.return_value = Mock()

    with (
        patch.dict("sys.modules", {"cv2": mock_cv2}),
        patch.object(eyetrack_plugin, "create_face_mesh", return_value=Mock()),
        patch.object(eyetrack_plugin, "estimate_pose", side_effect=pose_side_effect),
    ):
        eyetrack_plugin.tracking_active = True
        eyetrack_plugin.stop_event.clear()

        # Set stop_event after a short delay to prevent infinite loop in test
        import threading

        def stop_after_delay():
            time.sleep(0.5)
            eyetrack_plugin.stop_event.set()

        stopper = threading.Thread(target=stop_after_delay, daemon=True)
        stopper.start()

        eyetrack_plugin.run_tracking()

        # After run_tracking completes, tracking_active should be False
        assert eyetrack_plugin.tracking_active is False
        if webcam_opens:
            assert mock_cap.release.called


# --- Multi-monitor support ---------------------------------------------------

_TWO_MONITORS = [
    {"index": 0, "x": 0, "y": 0, "width": 1920, "height": 1080, "primary": True},
    {"index": 1, "x": 1920, "y": 0, "width": 2560, "height": 1440, "primary": False},
]


@patch.object(eyetrack_plugin, "host_run")
def test_get_monitors_parses_json(mock_host_run):
    """When the extension returns monitor JSON then get_monitors decodes it."""
    payload = json.dumps(_TWO_MONITORS)
    # gdbus wraps the string in a tuple with single quotes.
    mock_host_run.return_value = Mock(returncode=0, stdout=f"('{payload}',)\n")

    result = eyetrack_plugin.get_monitors()

    assert result == _TWO_MONITORS
    call_args = mock_host_run.call_args.args[0]
    assert call_args[8] == "org.EchoBase.Grid.GetMonitors"


@patch.object(eyetrack_plugin, "get_screen_size", return_value=(1920, 1080))
@patch.object(eyetrack_plugin, "host_run")
def test_get_monitors_falls_back_to_screen_size(mock_host_run, mock_screen):
    """When the extension call fails then get_monitors returns one screen."""
    mock_host_run.return_value = Mock(returncode=1, stdout="")

    result = eyetrack_plugin.get_monitors()

    assert result == [
        {"index": 0, "x": 0, "y": 0, "width": 1920, "height": 1080, "primary": True}
    ]


@patch.object(eyetrack_plugin, "get_monitors", return_value=_TWO_MONITORS)
def test_refresh_monitors_selects_primary(mock_get):
    """When refreshing then the active monitor resets to the primary one."""
    eyetrack_plugin.active_monitor = 1

    eyetrack_plugin.refresh_monitors()

    assert eyetrack_plugin.monitors == _TWO_MONITORS
    assert eyetrack_plugin.active_monitor == 0  # primary is index 0


def test_tracking_region_active_monitor():
    """In active mode the region is the selected monitor's rectangle."""
    eyetrack_plugin.monitors = _TWO_MONITORS
    eyetrack_plugin.monitor_mode = "active"
    eyetrack_plugin.active_monitor = 1

    assert eyetrack_plugin.tracking_region() == (1920, 0, 2560, 1440)


def test_tracking_region_span_is_bounding_box():
    """In span mode the region is the bounding box of all monitors."""
    eyetrack_plugin.monitors = _TWO_MONITORS
    eyetrack_plugin.monitor_mode = "span"

    # x spans 0..(1920+2560)=4480, y spans 0..1440
    assert eyetrack_plugin.tracking_region() == (0, 0, 4480, 1440)


@patch.object(eyetrack_plugin, "get_screen_size", return_value=(1280, 720))
def test_tracking_region_fallback_when_no_monitors(mock_screen):
    """With no known layout the region falls back to the primary screen size."""
    eyetrack_plugin.monitors = []

    assert eyetrack_plugin.tracking_region() == (0, 0, 1280, 720)


@patch.object(eyetrack_plugin, "dbus_call", return_value=True)
def test_switch_monitor_next_warps_to_center(mock_dbus):
    """Switching to the next monitor warps the cursor to its centre."""
    eyetrack_plugin.monitors = _TWO_MONITORS
    eyetrack_plugin.active_monitor = 0

    ok, msg = eyetrack_plugin.switch_monitor("next")

    assert ok is True
    assert msg == "Screen 2"
    assert eyetrack_plugin.active_monitor == 1
    assert eyetrack_plugin.cursor_x == 1920 + 2560 // 2
    assert eyetrack_plugin.cursor_y == 0 + 1440 // 2
    move = [c for c in mock_dbus.call_args_list if c.args[0] == "MoveTo"]
    assert len(move) == 1


@patch.object(eyetrack_plugin, "dbus_call", return_value=True)
def test_switch_monitor_prev_wraps(mock_dbus):
    """Previous from the first monitor wraps to the last."""
    eyetrack_plugin.monitors = _TWO_MONITORS
    eyetrack_plugin.active_monitor = 0

    ok, msg = eyetrack_plugin.switch_monitor("prev")

    assert ok is True
    assert eyetrack_plugin.active_monitor == 1


@patch.object(eyetrack_plugin, "dbus_call", return_value=True)
def test_switch_monitor_by_index(mock_dbus):
    """Switching by explicit index selects that monitor."""
    eyetrack_plugin.monitors = _TWO_MONITORS
    eyetrack_plugin.active_monitor = 0

    ok, msg = eyetrack_plugin.switch_monitor(1)

    assert ok is True
    assert eyetrack_plugin.active_monitor == 1


@patch.object(eyetrack_plugin, "dbus_call", return_value=True)
def test_switch_monitor_out_of_range(mock_dbus):
    """An out-of-range screen number is rejected without moving."""
    eyetrack_plugin.monitors = _TWO_MONITORS
    eyetrack_plugin.active_monitor = 0

    ok, msg = eyetrack_plugin.switch_monitor(5)

    assert ok is False
    assert "no screen 6" in msg.lower()
    assert eyetrack_plugin.active_monitor == 0
    assert not mock_dbus.called


def test_set_monitor_mode():
    """set_monitor_mode normalises to 'span' or 'active'."""
    assert eyetrack_plugin.set_monitor_mode("span") == "span"
    assert eyetrack_plugin.monitor_mode == "span"
    assert eyetrack_plugin.set_monitor_mode("anything else") == "active"
    assert eyetrack_plugin.monitor_mode == "active"


@patch.object(eyetrack_plugin, "get_screen_size", return_value=(1920, 1080))
@patch.object(eyetrack_plugin, "dbus_call", return_value=True)
def test_listen_for_tracking_commands_next_screen(
    mock_dbus, mock_screen_size, mock_core
):
    """'next screen' switches the active monitor while tracking."""
    eyetrack_plugin.tracking_active = True
    eyetrack_plugin.monitors = _TWO_MONITORS
    eyetrack_plugin.active_monitor = 0

    mock_core.wait_for_speech.side_effect = [b"a1", b"a2"]
    mock_core.record_until_silence.return_value = b"more"
    mock_core.transcribe.side_effect = ["next screen", "stop"]

    eyetrack_plugin.listen_for_tracking_commands(mock_core)

    assert eyetrack_plugin.active_monitor == 1
    assert mock_core.speak.call_args_list[0].args[0] == "Screen 2"


@patch.object(eyetrack_plugin, "get_screen_size", return_value=(1920, 1080))
@patch.object(eyetrack_plugin, "dbus_call", return_value=True)
def test_listen_for_tracking_commands_span_screens(
    mock_dbus, mock_screen_size, mock_core
):
    """'span screens' switches the tracker to span mode."""
    eyetrack_plugin.tracking_active = True
    eyetrack_plugin.monitor_mode = "active"

    mock_core.wait_for_speech.side_effect = [b"a1", b"a2"]
    mock_core.record_until_silence.return_value = b"more"
    mock_core.transcribe.side_effect = ["span screens", "stop"]

    eyetrack_plugin.listen_for_tracking_commands(mock_core)

    assert eyetrack_plugin.monitor_mode == "span"


# --- Camera availability / conflict detection --------------------------------


def _mock_cv2(opens, reads_ok):
    """Build a Mock cv2 whose VideoCapture opens (or not) and reads (or not)."""
    cap = Mock()
    cap.isOpened.return_value = opens
    cap.read.return_value = (True, Mock()) if reads_ok else (False, None)
    cv2 = Mock()
    cv2.VideoCapture.return_value = cap
    return cv2, cap


@patch.object(eyetrack_plugin, "list_camera_devices", return_value=[0])
def test_open_camera_busy_when_device_present_but_unreadable(mock_list):
    """A present-but-unreadable camera is reported as 'busy' (another app)."""
    cv2, cap = _mock_cv2(opens=True, reads_ok=False)
    with patch.dict("sys.modules", {"cv2": cv2}):
        result = eyetrack_plugin.open_camera()

    assert result == (None, None)
    assert eyetrack_plugin.camera_error == "busy"
    assert cap.release.called


@patch.object(eyetrack_plugin, "list_camera_devices", return_value=[])
def test_open_camera_missing_when_no_devices(mock_list):
    """With no /dev/video* devices the failure is reported as 'missing'."""
    cv2, cap = _mock_cv2(opens=False, reads_ok=False)
    with patch.dict("sys.modules", {"cv2": cv2}):
        result = eyetrack_plugin.open_camera()

    assert result == (None, None)
    assert eyetrack_plugin.camera_error == "missing"


@patch.object(eyetrack_plugin, "list_camera_devices", return_value=[0])
def test_open_camera_success_clears_error(mock_list):
    """A working camera returns (cap, index) and clears any prior error."""
    eyetrack_plugin.camera_error = "busy"
    cv2, cap = _mock_cv2(opens=True, reads_ok=True)
    with patch.dict("sys.modules", {"cv2": cv2}):
        result = eyetrack_plugin.open_camera()

    assert result == (cap, 0)
    assert eyetrack_plugin.camera_error is None


# --- Performance instrumentation ---------------------------------------------


def test_perf_monitor_reports_after_interval():
    """tick returns/prints a report only once the interval has elapsed."""
    pm = eyetrack_plugin.PerfMonitor(interval=2.0)
    pm.reset(now=100.0)

    # Within the window: accumulates but does not report.
    assert pm.tick(infer=0.05, read=0.01, move=0.005, loop=0.07, now=100.5) is None
    assert pm.tick(infer=0.05, read=0.01, move=0.005, loop=0.07, now=101.0) is None
    assert pm.frames == 2

    # Crossing the interval: emits a report and resets the window.
    line = pm.tick(infer=0.05, read=0.01, move=0.005, loop=0.07, now=102.5)
    assert line is not None
    assert "fps" in line and "infer" in line
    assert pm.frames == 0  # reset for the next window


def test_perf_monitor_report_fps_math():
    """The report reflects frames / elapsed wall time."""
    pm = eyetrack_plugin.PerfMonitor(interval=2.0)
    pm.reset(now=0.0)
    for i in range(10):
        pm.tick(infer=0.08, loop=0.09, now=0.1 * (i + 1))  # 10 frames in 1.0s
    # 10 frames over 1.0s -> ~10 fps; inference ~80ms.
    report = pm.report(now=1.0)
    assert "10.0 fps" in report
    assert "infer  80.0ms" in report


def test_perf_enabled_via_env(monkeypatch):
    """The env var force-enables perf stats regardless of config."""
    monkeypatch.setenv("ECHOBASE_TRACK_PERF", "1")
    eyetrack_plugin.core = None
    assert eyetrack_plugin.perf_enabled() is True


def test_perf_enabled_via_config(monkeypatch, mock_core):
    """The config flag enables perf stats when the env var is absent."""
    monkeypatch.delenv("ECHOBASE_TRACK_PERF", raising=False)
    mock_core.config = {"tracking_debug": True}
    eyetrack_plugin.core = mock_core
    assert eyetrack_plugin.perf_enabled() is True


def test_perf_disabled_by_default(monkeypatch):
    """With no env var and no config flag, perf stats stay off."""
    monkeypatch.delenv("ECHOBASE_TRACK_PERF", raising=False)
    eyetrack_plugin.core = None
    assert eyetrack_plugin.perf_enabled() is False


# --- MediaPipe Face Mesh head-pose estimation --------------------------------


def _fake_face_mesh(points):
    """Build a Mock Face Mesh whose process() returns one face with the given
    landmark coordinates ({index: (x, y)}); other landmarks default to centre."""
    lms = [Mock(x=0.5, y=0.5, z=0.0) for _ in range(468)]
    for idx, (x, y) in points.items():
        lms[idx].x = x
        lms[idx].y = y
    face = Mock()
    face.landmark = lms
    fm = Mock()
    fm.process.return_value = Mock(multi_face_landmarks=[face])
    return fm


def test_estimate_pose_centered_is_zero_yaw():
    """Nose centred on the eye line -> yaw 0; nose below eyes -> positive pitch."""
    # eyes at (0.4,0.4) & (0.6,0.4) -> centre (0.5,0.4), iod 0.2; nose (0.5,0.6)
    fm = _fake_face_mesh({1: (0.5, 0.6), 33: (0.4, 0.4), 263: (0.6, 0.4)})
    with patch.dict("sys.modules", {"cv2": Mock()}):
        yaw, pitch = eyetrack_plugin.estimate_pose(Mock(), fm)
    assert abs(yaw) < 0.01
    assert abs(pitch - 100.0) < 0.01  # (0.6-0.4)/0.2 * POSE_SCALE(100)


def test_estimate_pose_nose_right_gives_positive_yaw():
    """Nose shifted toward image-right (head turned right) -> yaw > 0."""
    fm = _fake_face_mesh({1: (0.55, 0.6), 33: (0.4, 0.4), 263: (0.6, 0.4)})
    with patch.dict("sys.modules", {"cv2": Mock()}):
        yaw, _ = eyetrack_plugin.estimate_pose(Mock(), fm)
    assert yaw > 0


def test_estimate_pose_distance_invariant():
    """Moving the whole face closer (uniformly scaled 1.5x about the centre)
    leaves the normalised signal unchanged."""
    near = _fake_face_mesh({1: (0.50, 0.65), 33: (0.35, 0.35), 263: (0.65, 0.35)})
    far = _fake_face_mesh({1: (0.50, 0.60), 33: (0.40, 0.40), 263: (0.60, 0.40)})
    with patch.dict("sys.modules", {"cv2": Mock()}):
        y1, p1 = eyetrack_plugin.estimate_pose(Mock(), near)
        y2, p2 = eyetrack_plugin.estimate_pose(Mock(), far)
    assert abs(y1 - y2) < 0.01  # both centred horizontally
    assert abs(p1 - p2) < 0.01  # same nose-below-eyes ratio despite different scale


def test_estimate_pose_no_face_returns_none():
    """No face detected -> None (loop skips the frame)."""
    fm = Mock()
    fm.process.return_value = Mock(multi_face_landmarks=[])
    with patch.dict("sys.modules", {"cv2": Mock()}):
        assert eyetrack_plugin.estimate_pose(Mock(), fm) is None


def test_create_face_mesh_uses_solutions_api():
    """create_face_mesh builds a single-face MediaPipe FaceMesh."""
    mp = Mock()
    with patch.dict("sys.modules", {"mediapipe": mp}):
        eyetrack_plugin.create_face_mesh()
    assert mp.solutions.face_mesh.FaceMesh.called
    kwargs = mp.solutions.face_mesh.FaceMesh.call_args.kwargs
    assert kwargs["max_num_faces"] == 1


def test_create_face_mesh_silences_protobuf_spam():
    """create_face_mesh installs a filter for protobuf's per-frame deprecation
    warning and quiets MediaPipe's C++ logs, so the console stays readable."""
    import warnings

    with patch.dict("sys.modules", {"mediapipe": Mock()}):
        eyetrack_plugin.create_face_mesh()

    assert any(
        action == "ignore"
        and msg is not None
        and msg.search("SymbolDatabase.GetPrototype() is deprecated")
        for (action, msg, *_rest) in warnings.filters
    )
    assert eyetrack_plugin.os.environ.get("GLOG_minloglevel") == "2"
