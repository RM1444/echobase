import json
import math
import os
import re
import subprocess
import threading
import time

from EchoBase.core import atspi, config

NAME = "headtrack"
DESCRIPTION = "Head tracking for cursor control"
PRIORITY = 0

COMMANDS = [
    "start tracking - begin head tracking",
    "stop tracking - end tracking",
    "freeze - lock cursor position",
    "go - resume tracking",
    "faster / slower - adjust tracking sensitivity live",
    "dwell on / dwell off - toggle hands-free auto-click on rest",
    "next screen / previous screen / screen two - move tracking to another monitor",
    "span screens / single screen - track all monitors as one, or just one",
    "nudge up/down/left/right - fine tune position",
    "click - left click at cursor",
    "double click - double click",
    "right click - right click",
    "recalibrate - reset center position",
]

core = None
tracking_active = False
tracking_thread = None
stop_event = threading.Event()
cursor_x = 960
cursor_y = 540
frozen = False
NUDGE_AMOUNT = 15

# Live tuning shared with the tracking thread.
sensitivity = 1.0  # multiplier on pixel/degree gain ("faster"/"slower")
_recalibrate = False  # set True to re-center without restarting the thread
camera_index = None  # the webcam index actually opened
camera_error = None  # why the last open_camera() failed: "busy" | "missing" | None

# Multi-monitor support. The pointer is driven in the compositor's global
# logical coordinate space (the union of all displays), so we map head pose into
# one monitor's rectangle at a time ("active" mode) and let the user hop between
# screens by voice, or treat every monitor as one continuous surface ("span").
monitors = []  # list of {"index","x","y","width","height","primary"} dicts
active_monitor = 0  # index into `monitors` that "active" mode tracks
monitor_mode = "active"  # "active" (one screen, switchable) or "span" (all)

# Spoken ordinals/digits -> zero-based monitor index ("screen two" -> 1).
_SCREEN_WORDS = {
    "one": 0,
    "first": 0,
    "1": 0,
    "two": 1,
    "second": 1,
    "2": 1,
    "three": 2,
    "third": 2,
    "3": 2,
    "tree": 2,
    "four": 3,
    "fourth": 3,
    "4": 3,
}

# Head-pose smoothing presets. Even MediaPipe landmarks jitter a little and can
# blip for a single frame, so each preset pairs a median pre-filter window (kills
# single-frame spikes) with One-Euro parameters (lower min_cutoff = smoother at
# rest; lower beta = smoother during motion) and a cursor-easing factor. Higher
# smoothing is steadier but adds a little latency.
SMOOTHING = {
    "low": {"median": 3, "min_cutoff": 1.0, "beta": 0.018, "ease": 0.7},
    "medium": {"median": 5, "min_cutoff": 0.5, "beta": 0.012, "ease": 0.4},
    "high": {"median": 7, "min_cutoff": 0.30, "beta": 0.008, "ease": 0.25},
}

# Snap-to-element ("hold onto a button"): while tracking, the cursor is gently
# pulled toward — and held on — the nearest clickable control, so it stops
# drifting off targets and a dwell click reliably lands. The control rectangles
# come from the AT-SPI tree (see atspi.get_clickables), refreshed on a slow timer
# in a background thread because the query is too heavy to run every frame.
snap_enabled = True
SNAP_RADIUS = 70  # px; only elements within this of the target attract the cursor
SNAP_STRENGTH = 0.55  # 0..1 fraction of the way pulled toward the element centre
SNAP_REFRESH = 0.7  # seconds between AT-SPI element-list refreshes
_snap_targets = []  # cached list of clickable rects (dicts: x, y, w, h, ...)
_snap_thread = None
_snap_stop = threading.Event()


def _snap_center(target_x, target_y):
    """Return a (x, y) pulled toward the nearest clickable element, or the input
    unchanged when none is close. If the point already sits inside an element,
    it is pulled harder so the cursor "holds" there instead of skimming off."""
    if not snap_enabled or not _snap_targets:
        return target_x, target_y

    best = None
    best_d2 = None
    for el in _snap_targets:
        cx = el["x"] + el["w"] / 2.0
        cy = el["y"] + el["h"] / 2.0
        inside = el["x"] <= target_x <= el["x"] + el["w"] and (
            el["y"] <= target_y <= el["y"] + el["h"]
        )
        d2 = (cx - target_x) ** 2 + (cy - target_y) ** 2
        # Inside elements always win over merely-near ones.
        rank = (0 if inside else 1, d2)
        if best is None or rank < best:
            best = rank
            best_d2 = d2
            best_el = el

    cx = best_el["x"] + best_el["w"] / 2.0
    cy = best_el["y"] + best_el["h"] / 2.0
    inside = best[0] == 0
    if not inside and best_d2 > SNAP_RADIUS**2:
        return target_x, target_y
    strength = 0.85 if inside else SNAP_STRENGTH
    return (
        target_x + (cx - target_x) * strength,
        target_y + (cy - target_y) * strength,
    )


def _snap_refresh_loop():
    """Background worker: periodically refresh the clickable-element cache."""
    global _snap_targets
    while not _snap_stop.is_set():
        if snap_enabled:
            try:
                _snap_targets = atspi.get_clickables()
            except Exception:
                _snap_targets = []
        _snap_stop.wait(SNAP_REFRESH)


def start_snap_refresher():
    global _snap_thread, _snap_targets
    _snap_targets = []
    _snap_stop.clear()
    _snap_thread = threading.Thread(target=_snap_refresh_loop, daemon=True)
    _snap_thread.start()


def stop_snap_refresher():
    global _snap_targets
    _snap_stop.set()
    _snap_targets = []


# Dwell click: auto-click when the cursor rests still long enough.
dwell_enabled = False
dwell_seconds = 1.5
DWELL_RADIUS = 30  # px; moving beyond this resets the dwell timer
_dwell_anchor = None
_dwell_start = 0.0
_dwell_clicked = False


def reset_dwell():
    global _dwell_anchor, _dwell_clicked
    _dwell_anchor = None
    _dwell_clicked = False


def dwell_update(now, cx, cy):
    """Advance the dwell-click state machine for the current cursor position.

    Returns one of:
      ("reset", 0.0)      cursor moved — hide the ring, timer restarted
      ("progress", frac)  resting — show the ring filled to ``frac``
      ("click", 1.0)      dwell elapsed — fire a click (once per rest)
      None                dwell disabled
    """
    global _dwell_anchor, _dwell_start, _dwell_clicked

    if not dwell_enabled:
        return None

    moved = _dwell_anchor is None or (
        abs(cx - _dwell_anchor[0]) > DWELL_RADIUS
        or abs(cy - _dwell_anchor[1]) > DWELL_RADIUS
    )
    if moved:
        _dwell_anchor = (cx, cy)
        _dwell_start = now
        _dwell_clicked = False
        return ("reset", 0.0)

    if _dwell_clicked:
        # Already clicked at this spot — stay quiet until the cursor moves away.
        return ("held", 1.0)

    elapsed = now - _dwell_start
    frac = min(1.0, elapsed / max(0.1, dwell_seconds))
    if elapsed >= dwell_seconds:
        _dwell_clicked = True
        return ("click", 1.0)
    return ("progress", frac)


_dwell_visible = False


def dwell_tick(cx, cy):
    """Run one dwell step at (cx, cy): update the on-screen ring and fire a
    click when the dwell completes. Returns True if a click was issued."""
    global _dwell_visible

    res = dwell_update(time.time(), int(cx), int(cy))
    if res is None:  # dwell disabled
        if _dwell_visible:
            dbus_call("HideDwell")
            _dwell_visible = False
        return False

    kind, frac = res
    if kind in ("reset", "held"):
        if _dwell_visible:
            dbus_call("HideDwell")
            _dwell_visible = False
    elif kind == "progress":
        dbus_call("ShowDwell", int(cx), int(cy), round(frac, 2))
        _dwell_visible = True
    elif kind == "click":
        if _dwell_visible:
            dbus_call("HideDwell")
            _dwell_visible = False
        dbus_call("Click", int(cx), int(cy))
        return True
    return False


class OneEuroFilter:
    """
    One-Euro Filter for smoothing noisy signals.
    Adapts: smooth when still, responsive when moving.
    """

    def __init__(self, freq=30.0, min_cutoff=1.0, beta=0.007, d_cutoff=1.0):
        self.freq = freq
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.x_prev = None
        self.dx_prev = 0.0
        self.t_prev = None

    def _alpha(self, cutoff):
        tau = 1.0 / (2.0 * math.pi * cutoff)
        te = 1.0 / self.freq
        return 1.0 / (1.0 + tau / te)

    def __call__(self, x, t=None):
        if self.x_prev is None:
            self.x_prev = x
            self.t_prev = t
            return x

        # When a real timestamp is supplied, derive the true sampling rate from
        # the gap between frames so the smoothing tracks the actual (variable,
        # CPU-bound) frame rate instead of an assumed 30 fps. Clamp it so a
        # microsecond hiccup can't make the filter ignore new input, nor a long
        # stall make it hyper-twitchy. Without a timestamp we keep ``freq``.
        if t is not None and self.t_prev is not None:
            dt = t - self.t_prev
            if dt > 0:
                self.freq = max(5.0, min(120.0, 1.0 / dt))
        self.t_prev = t

        # Derivative
        dx = (x - self.x_prev) * self.freq

        # Smooth derivative
        a_d = self._alpha(self.d_cutoff)
        dx_smooth = a_d * dx + (1 - a_d) * self.dx_prev
        self.dx_prev = dx_smooth

        # Adaptive cutoff based on speed
        cutoff = self.min_cutoff + self.beta * abs(dx_smooth)

        # Smooth value
        a = self._alpha(cutoff)
        x_smooth = a * x + (1 - a) * self.x_prev
        self.x_prev = x_smooth

        return x_smooth


def setup(c):
    global core
    core = c


def host_run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def dbus_call(method, *args):
    """Call GNOME Shell extension for cursor movement"""
    cmd = [
        "gdbus",
        "call",
        "--session",
        "--dest",
        "org.gnome.Shell",
        "--object-path",
        "/org/EchoBase/Grid",
        "--method",
        f"org.EchoBase.Grid.{method}",
    ]
    cmd.extend(str(a) for a in args)
    result = host_run(cmd)
    return result.returncode == 0


def get_screen_size():
    """Get screen size from GNOME Shell extension"""
    result = host_run(
        [
            "gdbus",
            "call",
            "--session",
            "--dest",
            "org.gnome.Shell",
            "--object-path",
            "/org/EchoBase/Grid",
            "--method",
            "org.EchoBase.Grid.GetScreenSize",
        ]
    )

    if result.returncode == 0:
        match = re.search(r"\((\d+),\s*(\d+)\)", result.stdout)
        if match:
            return int(match.group(1)), int(match.group(2))
    return 1920, 1080


def get_monitors():
    """Query the extension for every monitor's geometry (global logical coords).

    Returns a list of monitor dicts. Falls back to a single monitor derived from
    ``get_screen_size`` if the extension is unavailable or its reply can't be
    parsed, so single-display setups keep working unchanged."""
    result = host_run(
        [
            "gdbus",
            "call",
            "--session",
            "--dest",
            "org.gnome.Shell",
            "--object-path",
            "/org/EchoBase/Grid",
            "--method",
            "org.EchoBase.Grid.GetMonitors",
        ]
    )
    if result.returncode == 0:
        # gdbus wraps the JSON string in a tuple: ('[{...}]',) — pull it out.
        match = re.search(r"'(.*)'", result.stdout or "", re.S)
        payload = match.group(1) if match else (result.stdout or "")
        try:
            data = json.loads(payload)
            if isinstance(data, list) and data:
                return data
        except (json.JSONDecodeError, ValueError):
            pass

    w, h = get_screen_size()
    return [{"index": 0, "x": 0, "y": 0, "width": w, "height": h, "primary": True}]


def refresh_monitors():
    """Re-read the monitor layout and reset the active monitor to the primary."""
    global monitors, active_monitor
    monitors = get_monitors()
    active_monitor = next((i for i, m in enumerate(monitors) if m.get("primary")), 0)
    return monitors


def tracking_region():
    """The rectangle (x, y, w, h) head pose currently maps into, in global
    coords. In "span" mode it's the bounding box of every monitor; in "active"
    mode it's the selected monitor. Falls back to the primary screen size when
    no monitor layout is known (e.g. before tracking has started)."""
    mons = monitors
    if not mons:
        w, h = get_screen_size()
        return (0, 0, w, h)

    if monitor_mode == "span":
        x0 = min(m["x"] for m in mons)
        y0 = min(m["y"] for m in mons)
        x1 = max(m["x"] + m["width"] for m in mons)
        y1 = max(m["y"] + m["height"] for m in mons)
        return (x0, y0, x1 - x0, y1 - y0)

    idx = active_monitor if 0 <= active_monitor < len(mons) else 0
    m = mons[idx]
    return (m["x"], m["y"], m["width"], m["height"])


def switch_monitor(target):
    """Point head tracking at another monitor and warp the cursor to its centre.

    ``target`` is a zero-based index, or the strings ``"next"`` / ``"prev"``.
    Returns ``(ok, spoken_message)``."""
    global active_monitor, cursor_x, cursor_y
    if not monitors:
        refresh_monitors()
    mons = monitors
    if not mons:
        return False, "I couldn't find any monitors."
    n = len(mons)

    if target == "next":
        active_monitor = (active_monitor + 1) % n
    elif target == "prev":
        active_monitor = (active_monitor - 1) % n
    else:
        if not (0 <= target < n):
            return False, f"There's no screen {target + 1}. You have {n}."
        active_monitor = target

    m = mons[active_monitor]
    cursor_x = m["x"] + m["width"] // 2
    cursor_y = m["y"] + m["height"] // 2
    dbus_call("MoveTo", int(cursor_x), int(cursor_y))
    return True, f"Screen {active_monitor + 1}"


def set_monitor_mode(mode):
    """Switch between per-monitor ("active") and all-screens ("span") tracking."""
    global monitor_mode
    monitor_mode = "span" if mode == "span" else "active"
    return monitor_mode


def list_camera_devices():
    """Indices of the /dev/video* nodes that exist (cameras present on the
    system, whether or not they're free). Used to tell "no camera" apart from
    "camera busy"."""
    import glob

    idxs = []
    for path in glob.glob("/dev/video*"):
        m = re.search(r"/dev/video(\d+)$", path)
        if m:
            idxs.append(int(m.group(1)))
    return sorted(idxs)


def open_camera():
    """Open a working webcam. Honours the configured index, otherwise probes
    common indices. Returns (cap, index) or (None, None).

    On failure sets the module-level ``camera_error`` so the caller can give an
    accurate spoken reason:
      "missing" — no camera devices exist on the system.
      "busy"    — a camera exists but couldn't be grabbed (almost always because
                  another app, e.g. a video-call or the Camera app, holds it;
                  V4L2 capture is single-owner)."""
    global camera_error
    import cv2

    camera_error = None
    present = list_camera_devices()

    pref = getattr(core, "config", {}).get("tracking_camera", "auto")
    order = []
    if isinstance(pref, int):
        order.append(pref)
    elif isinstance(pref, str) and pref.isdigit():
        order.append(int(pref))
    order += [0, 1, 2, 3]

    seen = set()
    for idx in order:
        if idx in seen:
            continue
        seen.add(idx)
        cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 30)
            # Retry a few frames: a real camera may need a moment to warm up,
            # while a busy one keeps failing (can't start streaming).
            ok = False
            for _ in range(3):
                ok, _frame = cap.read()
                if ok:
                    break
                time.sleep(0.05)
            if ok:
                print(f"Webcam opened on index {idx}")
                return cap, idx
        cap.release()

    # Nothing usable. If devices physically exist, the most common cause by far
    # is another app holding the camera; otherwise there's simply no camera.
    camera_error = "busy" if present else "missing"
    return None, None


# --- Head pose via MediaPipe Face Mesh ---------------------------------------
# We track facial landmarks (fast, ~30 fps on CPU, temporally stable) rather than
# a per-frame head-pose regressor. The control signal is the nose tip's position
# relative to the eye-line centre, normalised by inter-ocular distance — i.e.
# head orientation, invariant to how far the user sits from the camera. This is
# the classic, robust "head mouse" signal used by accessibility tools.
_NOSE_TIP = 1  # Face Mesh 468-landmark topology
_EYE_OUTER_A = 33  # outer corner of one eye
_EYE_OUTER_B = 263  # outer corner of the other eye
POSE_SCALE = 100.0  # scales the nose-vs-eyes ratio into a degrees-like range


def create_face_mesh():
    """Create a MediaPipe Face Mesh tracker (single face, streaming/video mode)."""
    import warnings

    # MediaPipe and its protobuf dependency are chatty: protobuf emits a
    # deprecation UserWarning on every frame, and MediaPipe's C++ core logs
    # INFO/WARNING lines to stderr. Quiet both so the console (and the
    # tracking_debug output) stays readable.
    os.environ.setdefault("GLOG_minloglevel", "2")
    warnings.filterwarnings("ignore", message=r".*GetPrototype\(\) is deprecated.*")

    import mediapipe as mp

    return mp.solutions.face_mesh.FaceMesh(
        static_image_mode=False,
        max_num_faces=1,
        refine_landmarks=False,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )


def estimate_pose(frame, face_mesh):
    """Return a (yaw, pitch) head-orientation signal from one BGR frame, or None
    when no face is found.

    yaw   > 0 : head turned toward the (mirrored) right  -> cursor moves right
    pitch > 0 : head tilted down                         -> cursor moves down
    The values are the nose tip's offset from the eye-line centre divided by the
    inter-ocular distance (so leaning closer/further doesn't change them) and
    scaled to a degrees-like range so the existing calibration / dead-zone /
    HEAD_RANGE constants apply unchanged."""
    import cv2

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    result = face_mesh.process(rgb)
    if not result.multi_face_landmarks:
        return None

    lm = result.multi_face_landmarks[0].landmark
    nose = lm[_NOSE_TIP]
    eye_a, eye_b = lm[_EYE_OUTER_A], lm[_EYE_OUTER_B]
    eye_cx = (eye_a.x + eye_b.x) / 2.0
    eye_cy = (eye_a.y + eye_b.y) / 2.0
    iod = math.hypot(eye_a.x - eye_b.x, eye_a.y - eye_b.y) or 1e-6
    yaw = (nose.x - eye_cx) / iod * POSE_SCALE
    pitch = (nose.y - eye_cy) / iod * POSE_SCALE
    return yaw, pitch


def perf_enabled():
    """Whether to print head-tracking performance stats. Opt-in via the
    ``ECHOBASE_TRACK_PERF`` env var or ``"tracking_debug": true`` in the config,
    so normal runs stay quiet."""
    if os.environ.get("ECHOBASE_TRACK_PERF"):
        return True
    cfg = getattr(core, "config", {}) or {}
    return bool(cfg.get("tracking_debug"))


class PerfMonitor:
    """Rolling head-tracking performance counters.

    Call :meth:`tick` once per processed frame with how long each stage took;
    every ``interval`` seconds it prints a one-line report and resets. This is
    the instrument for diagnosing lag: it shows the true frame rate and exactly
    where the per-frame time goes (camera read vs model inference vs cursor
    move). ``now`` is injectable for testing."""

    def __init__(self, interval=2.0):
        self.interval = interval
        self.reset(now=0.0)

    def reset(self, now=None):
        self.frames = 0
        self.infer = 0.0
        self.read = 0.0
        self.move = 0.0
        self.loop = 0.0
        self.window_start = time.time() if now is None else now

    def tick(self, *, infer=0.0, read=0.0, move=0.0, loop=0.0, now=None):
        """Record one frame. Returns the report string when a window elapsed."""
        now = time.time() if now is None else now
        self.frames += 1
        self.infer += infer
        self.read += read
        self.move += move
        self.loop += loop
        if now - self.window_start >= self.interval:
            line = self.report(now)
            print(line)
            self.reset(now=now)
            return line
        return None

    def report(self, now=None):
        now = time.time() if now is None else now
        elapsed = max(1e-6, now - self.window_start)
        n = max(1, self.frames)
        fps = self.frames / elapsed
        return (
            f"[headtrack] {fps:4.1f} fps over {self.frames} frames | "
            f"infer {1000 * self.infer / n:5.1f}ms | "
            f"read {1000 * self.read / n:4.1f}ms | "
            f"move {1000 * self.move / n:4.1f}ms | "
            f"loop {1000 * self.loop / n:5.1f}ms (avg/frame)"
        )


def _record(perf, loop_t0, read_dt, infer_dt, move_dt=0.0):
    """Feed one frame's timings to the perf monitor (no-op when disabled)."""
    if perf is not None:
        perf.tick(
            infer=infer_dt, read=read_dt, move=move_dt, loop=time.time() - loop_t0
        )


def run_tracking():
    """Main tracking loop"""
    global tracking_active, stop_event, cursor_x, cursor_y, frozen
    global _recalibrate, camera_index

    import cv2

    perf = PerfMonitor() if perf_enabled() else None

    # Tracking region in the compositor's global coordinate space (one monitor,
    # or all of them in "span" mode). Recomputed each frame so a spoken
    # "next screen" / "span screens" takes effect live.
    region = tracking_region()
    print(f"Tracking region: {region} (mode={monitor_mode})")

    cap, camera_index = open_camera()
    if cap is None:
        print(f"Cannot open any webcam! ({camera_error})")
        if core:
            if camera_error == "busy":
                core.speak(
                    "The camera looks like it's being used by another app. "
                    "Close it, then say start tracking again."
                )
            else:
                core.speak("I couldn't find a working webcam for head tracking.")
        tracking_active = False
        return

    print("Loading MediaPipe Face Mesh...")
    load_t0 = time.time()
    face_mesh = create_face_mesh()
    if perf is not None:
        print(f"[headtrack] face mesh load: {time.time() - load_t0:.2f}s (CPU)")

    # Two-stage smoothing, tuned by the `tracking_smoothing` preset:
    #   1) a short MEDIAN window over the raw angles removes single-frame pose
    #      spikes (the model occasionally returns one wildly wrong angle), and
    #   2) a One-Euro filter (fed real per-frame timestamps) smooths the residual
    #      jitter — heavy when the head is still, light during a deliberate move.
    cfg = getattr(core, "config", {}) or {}
    sm = SMOOTHING.get(cfg.get("tracking_smoothing", "medium"), SMOOTHING["medium"])
    MEDIAN_WINDOW = sm["median"]
    # Cursor easing: each frame the pointer moves only this fraction of the way to
    # its target, a position-domain low-pass that smooths residual angle jitter
    # (1.0 = snap straight to target, lower = glide more smoothly).
    CURSOR_EASE = sm["ease"]
    yaw_hist = []
    pitch_hist = []
    filter_yaw = OneEuroFilter(min_cutoff=sm["min_cutoff"], beta=sm["beta"])
    filter_pitch = OneEuroFilter(min_cutoff=sm["min_cutoff"], beta=sm["beta"])
    print(
        f"[headtrack] smoothing: median={MEDIAN_WINDOW} "
        f"one-euro={sm['min_cutoff']} ease={CURSOR_EASE}"
    )

    # Last integer position actually sent to the compositor, so redundant MoveTo
    # calls (one gdbus spawn per frame otherwise) can be skipped.
    last_sent = (None, None)

    # Calibration center
    center_yaw = None
    center_pitch = None

    # Settings. HEAD_RANGE_* is how many degrees of head movement from centre
    # reach the edge of the region — the mapping is linear within it, so the
    # pointer tracks the head proportionally instead of slamming to the edges.
    # Lower = less head motion to cross the screen (more sensitive).
    HEAD_RANGE_X = 20.0  # degrees of yaw to reach the left/right edge
    HEAD_RANGE_Y = 15.0  # degrees of pitch to reach the top/bottom edge
    DEAD_ZONE = 3.0  # Degrees - ignore small movements (jitter)

    # Initialize cursor at the centre of the active region.
    cursor_x = region[0] + region[2] // 2
    cursor_y = region[1] + region[3] // 2
    prev_region = region

    print("Head tracking started. Look at center of screen...")
    print("Say 'recalibrate' to reset center, 'stop tracking' to end")

    calibration_frames = 0
    calibration_yaw = 0.0
    calibration_pitch = 0.0
    dbg_t = 0.0  # throttle for the angle-debug line (tracking_debug only)

    while tracking_active and not stop_event.is_set():
        loop_t0 = time.time()
        read_dt = infer_dt = move_dt = 0.0

        # Instant recalibrate: re-center over the next few frames, no restart.
        if _recalibrate:
            center_yaw = None
            center_pitch = None
            calibration_frames = 0
            calibration_yaw = 0.0
            calibration_pitch = 0.0
            filter_yaw.x_prev = None
            filter_pitch.x_prev = None
            yaw_hist.clear()
            pitch_hist.clear()
            last_sent = (None, None)
            _recalibrate = False
            print("Recalibrating center...")

        # Pick up live monitor changes ("next screen", "span screens"): when the
        # region shifts, jump the cursor to its centre so head-forward maps there.
        region = tracking_region()
        if region != prev_region:
            cursor_x = region[0] + region[2] // 2
            cursor_y = region[1] + region[3] // 2
            last_sent = (None, None)
            prev_region = region

        read_t0 = time.time()
        ret, frame = cap.read()
        read_dt = time.time() - read_t0
        if not ret:
            time.sleep(0.01)  # camera hiccup — back off instead of busy-spinning
            continue

        frame = cv2.flip(frame, 1)  # Mirror

        infer_t0 = time.time()
        pose = estimate_pose(frame, face_mesh)
        infer_dt = time.time() - infer_t0

        if pose is None:  # no face in view this frame
            _record(perf, loop_t0, read_dt, infer_dt)
            continue

        raw_yaw, raw_pitch = pose

        # Median pre-filter: replace each axis with the median of the last few
        # frames, which drops single-frame pose spikes before they reach the
        # smoother (or bias calibration). Window of 1 is a no-op (low preset).
        yaw_hist.append(raw_yaw)
        pitch_hist.append(raw_pitch)
        if len(yaw_hist) > MEDIAN_WINDOW:
            yaw_hist.pop(0)
            pitch_hist.pop(0)
        raw_yaw = sorted(yaw_hist)[len(yaw_hist) // 2]
        raw_pitch = sorted(pitch_hist)[len(pitch_hist) // 2]

        # Auto-calibrate on first 10 frames
        if center_yaw is None:
            calibration_yaw += raw_yaw
            calibration_pitch += raw_pitch
            calibration_frames += 1

            if calibration_frames >= 10:
                center_yaw = calibration_yaw / 10
                center_pitch = calibration_pitch / 10
                print(f"Calibrated: center=({center_yaw:.1f}, {center_pitch:.1f})")
            _record(perf, loop_t0, read_dt, infer_dt)
            continue

        # Single-stage smoothing: feed the One-Euro filter the real frame time
        # so its cutoff tracks the actual frame rate, and use its output
        # directly — no extra moving average. This is what removes the lag.
        now = time.time()
        avg_yaw = filter_yaw(raw_yaw, now)
        avg_pitch = filter_pitch(raw_pitch, now)

        # Angle probe: with tracking_debug on, print the head-orientation signal
        # vs the calibrated centre a few times a second. Look up/down/left/right
        # in turn and watch the offset signs swing both ways.
        if perf is not None and now - dbg_t >= 0.3:
            dbg_t = now
            print(
                f"[headtrack] raw yaw={raw_yaw:+6.1f} pitch={raw_pitch:+6.1f} | "
                f"filtered yaw={avg_yaw:+6.1f} pitch={avg_pitch:+6.1f} | "
                f"center=({center_yaw:+.1f},{center_pitch:+.1f}) | "
                f"offset yaw={avg_yaw - center_yaw:+6.1f} pitch={avg_pitch - center_pitch:+6.1f}"
            )

        # (No velocity gate: the median + One-Euro + cursor easing below keep a
        # resting cursor steady without freezing it short of its target, which a
        # hard gate would do now that the cursor eases rather than snaps.)

        # Offset from center
        offset_yaw = avg_yaw - center_yaw
        offset_pitch = avg_pitch - center_pitch

        # Dead zone
        if abs(offset_yaw) < DEAD_ZONE:
            offset_yaw = 0
        else:
            offset_yaw = (
                offset_yaw - DEAD_ZONE if offset_yaw > 0 else offset_yaw + DEAD_ZONE
            )

        if abs(offset_pitch) < DEAD_ZONE:
            offset_pitch = 0
        else:
            offset_pitch = (
                offset_pitch - DEAD_ZONE
                if offset_pitch > 0
                else offset_pitch + DEAD_ZONE
            )

        # Linear, proportional mapping into the active region (which may sit at a
        # non-zero origin on a secondary monitor). A head offset of HEAD_RANGE_*
        # degrees reaches the edge; everything in between maps 1:1. `sensitivity`
        # is the live multiplier from "faster"/"slower" (and the saved
        # preference) — higher means less head movement to cross the screen.
        rx, ry, rw, rh = region
        gain_x = (rw / 2.0) / HEAD_RANGE_X
        gain_y = (rh / 2.0) / HEAD_RANGE_Y
        target_x = rx + rw / 2.0 + offset_yaw * gain_x * sensitivity
        target_y = ry + rh / 2.0 + offset_pitch * gain_y * sensitivity

        # Clamp target to the region FIRST
        target_x = max(rx, min(rx + rw - 1, target_x))
        target_y = max(ry, min(ry + rh - 1, target_y))

        # Edge dampening - slow down as we approach edges/corners
        EDGE_MARGIN = 150  # Pixels from edge where dampening kicks in
        MIN_DAMP = 0.3  # Minimum speed at very edge (0.3 = 30% speed)

        # Calculate distance from the region's edges
        dist_left = target_x - rx
        dist_right = rx + rw - 1 - target_x
        dist_top = target_y - ry
        dist_bottom = ry + rh - 1 - target_y

        # Find closest edge distance
        closest_x = min(dist_left, dist_right)
        closest_y = min(dist_top, dist_bottom)

        # Dampening: 1.0 when far from edge, MIN_DAMP at edge
        damp_x = (
            1.0
            if closest_x > EDGE_MARGIN
            else MIN_DAMP + (1.0 - MIN_DAMP) * (closest_x / EDGE_MARGIN)
        )
        damp_y = (
            1.0
            if closest_y > EDGE_MARGIN
            else MIN_DAMP + (1.0 - MIN_DAMP) * (closest_y / EDGE_MARGIN)
        )

        # Blend toward the target: ease globally for smoothness (CURSOR_EASE),
        # and slow further near edges/corners (damp_x/damp_y).
        damp = min(damp_x, damp_y, CURSOR_EASE)

        # Snap-to-element: bias the target toward (and hold on) the nearest
        # clickable control so the cursor stops drifting off buttons and a dwell
        # click lands reliably. No-op when disabled or nothing is close.
        if snap_enabled:
            target_x, target_y = _snap_center(target_x, target_y)

        # Apply cursor position update (only if not frozen)
        if not frozen:
            # Edge dampening blends toward the target near the screen borders;
            # in the central region damp == 1.0, so the cursor tracks the head
            # 1:1 with no added latency.
            cursor_x = cursor_x + (target_x - cursor_x) * damp
            cursor_y = cursor_y + (target_y - cursor_y) * damp

            # Strictly clamp to the region bounds
            cursor_x = max(rx + 5, min(rx + rw - 5, cursor_x))
            cursor_y = max(ry + 5, min(ry + rh - 5, cursor_y))

            # Only talk to the compositor when the integer position actually
            # changed — avoids spawning a gdbus process for a no-op move.
            ix, iy = int(cursor_x), int(cursor_y)
            # Publish the live cursor so other plugins (e.g. global scroll) can
            # act at the pointer while tracking runs.
            if core is not None:
                core._tracking_pos = (ix, iy)
            if (ix, iy) != last_sent:
                move_t0 = time.time()
                dbus_call("MoveTo", ix, iy)
                move_dt = time.time() - move_t0
                last_sent = (ix, iy)

            # Dwell click: moving resets the timer/ring; resting fires a click.
            dwell_tick(cursor_x, cursor_y)

        # No artificial frame cap: face-mesh inference is the natural throttle,
        # so the loop runs as fast as it allows for the lowest latency.
        _record(perf, loop_t0, read_dt, infer_dt, move_dt)

    cap.release()
    face_mesh.close()
    tracking_active = False
    print("Tracking stopped.")


def start_tracking():
    global tracking_active, tracking_thread, stop_event, frozen, sensitivity

    if tracking_active:
        return False, "Already tracking"

    # Seed live sensitivity + dwell from the saved accessibility preferences.
    cfg = getattr(core, "config", {})
    sensitivity = config.tracking_multiplier(cfg.get("tracking_sensitivity", "normal"))
    global dwell_enabled, dwell_seconds, monitor_mode, snap_enabled
    dwell_enabled = bool(cfg.get("dwell_enabled", False))
    dwell_seconds = float(cfg.get("dwell_seconds", 1.5))
    snap_enabled = bool(cfg.get("tracking_snap", True))
    reset_dwell()

    # Start the snap-to-element cache refresher and mark the mode active so the
    # core won't try to enter a second blocking mode over the top of tracking.
    start_snap_refresher()
    if core is not None:
        core.active_mode = "headtrack"

    # Discover the monitor layout and the preferred multi-monitor mode so the
    # cursor can reach every display.
    monitor_mode = "span" if cfg.get("tracking_monitor_mode") == "span" else "active"
    refresh_monitors()

    frozen = False
    stop_event.clear()
    tracking_active = True
    tracking_thread = threading.Thread(target=run_tracking, daemon=True)
    tracking_thread.start()
    return True, "Tracking"


def stop_tracking():
    global tracking_active, stop_event
    stop_event.set()
    tracking_active = False
    stop_snap_refresher()
    if core is not None:
        core.active_mode = None
        core._tracking_pos = None
    time.sleep(0.2)
    return True, "Stopped"


def recalibrate():
    """Re-center instantly by signalling the running thread (no restart)."""
    global _recalibrate
    if tracking_active:
        _recalibrate = True
        return True, "Recalibrating"
    return False, "Not tracking"


def adjust_sensitivity(faster):
    """Bump the live tracking sensitivity up or down. Returns the new value."""
    global sensitivity
    if faster:
        sensitivity = min(3.0, sensitivity * 1.3)
    else:
        sensitivity = max(0.2, sensitivity / 1.3)
    return sensitivity


def handle(cmd, core):
    global cursor_x, cursor_y
    cmd_lower = cmd.lower()

    # Start tracking
    if any(
        w in cmd_lower for w in ["start tracking", "begin tracking", "enable tracking"]
    ):
        success, msg = start_tracking()
        core.speak(msg)
        if success:
            listen_for_tracking_commands(core)
        return True

    # Stop tracking
    if any(
        w in cmd_lower
        for w in [
            "stop tracking",
            "end tracking",
            "close tracking",
            "quit tracking",
            "disable tracking",
            "tracking off",
            "stop track",
        ]
    ):
        success, msg = stop_tracking()
        core.speak(msg)
        return True

    # Recalibrate
    if "recalibrate" in cmd_lower or "calibrate" in cmd_lower:
        success, msg = recalibrate()
        core.speak(msg)
        return True

    return None


def listen_for_tracking_commands(core):
    """Continuous listening while tracking active"""
    global tracking_active, cursor_x, cursor_y, frozen, dwell_enabled

    print("Tracking mode: freeze, nudge, click, switch screen, or stop tracking")

    while tracking_active:
        try:
            core.stream.read(
                core.stream.get_read_available(), exception_on_overflow=False
            )
        except:
            pass

        first = core.wait_for_speech(timeout=10)
        if not first:
            continue

        audio = first + core.record_until_silence()
        cmd = core.transcribe(
            audio,
            prompt="click double click right click freeze go nudge up down left right recalibrate next screen previous screen monitor display span all screens single screen stop tracking close cancel",
        )
        if not cmd:
            continue

        cmd_lower = cmd.lower().strip()
        print(f"  ← {cmd_lower}")

        # Exit commands
        if any(
            w in cmd_lower
            for w in [
                "stop tracking",
                "end tracking",
                "close tracking",
                "stop",
                "cancel",
                "escape",
                "exit",
                "quit",
                "done",
            ]
        ):
            frozen = False
            stop_tracking()
            core.speak("Stopped")
            return

        # Freeze/Go
        if any(w in cmd_lower for w in ["freeze", "free", "rees", "frees"]):
            frozen = True
            print(f"  → Frozen at ({int(cursor_x)}, {int(cursor_y)})")
            continue

        if cmd_lower in ["go", "go go", "unfreeze", "resume", "track"]:
            frozen = False
            print("  → Resumed")
            continue

        # Dwell click on/off (hands-free auto-click while resting)
        if (
            "dwell" in cmd_lower
            or "hover click" in cmd_lower
            or "auto click" in cmd_lower
        ):
            if "off" in cmd_lower or "stop" in cmd_lower or "disable" in cmd_lower:
                dwell_enabled = False
                reset_dwell()
                dbus_call("HideDwell")
                core.speak("Dwell click off.")
            else:
                dwell_enabled = True
                reset_dwell()
                core.speak("Dwell click on.")
            continue

        # Snap-to-button on/off (hold the cursor onto the nearest control).
        if "snap" in cmd_lower or "magnet" in cmd_lower:
            global snap_enabled
            if "off" in cmd_lower or "stop" in cmd_lower or "disable" in cmd_lower:
                snap_enabled = False
                core.speak("Snap off.")
            else:
                snap_enabled = True
                core.speak("Snap on.")
            continue

        # Multi-monitor: mode toggle first, then per-screen switching.
        if any(
            p in cmd_lower
            for p in ["span", "all screens", "all monitors", "both screens"]
        ):
            set_monitor_mode("span")
            core.speak("Tracking all screens.")
            continue
        if any(
            p in cmd_lower
            for p in ["single screen", "single monitor", "one screen", "this screen"]
        ):
            set_monitor_mode("active")
            core.speak("Tracking one screen.")
            continue
        if any(w in cmd_lower for w in ["screen", "monitor", "display"]):
            if "next" in cmd_lower:
                ok, msg = switch_monitor("next")
            elif any(w in cmd_lower for w in ["previous", "prev", "last", "back"]):
                ok, msg = switch_monitor("prev")
            else:
                idx = next(
                    (_SCREEN_WORDS[w] for w in cmd_lower.split() if w in _SCREEN_WORDS),
                    None,
                )
                ok, msg = switch_monitor(idx if idx is not None else "next")
            core.speak(msg)
            continue

        # Live sensitivity (check before nudge so "speed up" isn't a nudge)
        if any(
            w in cmd_lower
            for w in ["faster", "speed up", "more sensitive", "quicker", "too slow"]
        ):
            new = adjust_sensitivity(True)
            core.speak("Faster.")
            print(f"  → Sensitivity {new:.2f}")
            continue
        if any(
            w in cmd_lower
            for w in ["slower", "slow down", "less sensitive", "too fast"]
        ):
            new = adjust_sensitivity(False)
            core.speak("Slower.")
            print(f"  → Sensitivity {new:.2f}")
            continue

        # Nudge (only when frozen) — clamp within the active region's bounds.
        if frozen and any(
            w in cmd_lower for w in ["nudge", "move", "up", "down", "left", "right"]
        ):
            rx, ry, rw, rh = tracking_region()
            if any(w in cmd_lower for w in ["up", "north"]):
                cursor_y = max(ry, cursor_y - NUDGE_AMOUNT)
            if any(w in cmd_lower for w in ["down", "south"]):
                cursor_y = min(ry + rh - 1, cursor_y + NUDGE_AMOUNT)
            if any(w in cmd_lower for w in ["left", "west"]):
                cursor_x = max(rx, cursor_x - NUDGE_AMOUNT)
            if any(w in cmd_lower for w in ["right", "east", "write"]):
                cursor_x = min(rx + rw - 1, cursor_x + NUDGE_AMOUNT)
            dbus_call("MoveTo", int(cursor_x), int(cursor_y))
            continue

        # Recalibrate
        if "recalibrate" in cmd_lower or "calibrate" in cmd_lower:
            frozen = False
            recalibrate()
            core.speak("Recalibrating")
            continue

        # Click commands
        if "double" in cmd_lower:
            dbus_call("DoubleClick", int(cursor_x), int(cursor_y))
            continue

        if any(w in cmd_lower for w in ["right click", "right-click", "write click"]):
            dbus_call("RightClick", int(cursor_x), int(cursor_y))
            continue

        if any(
            w in cmd_lower
            for w in ["click", "select", "press", "kick", "quick", "flick"]
        ):
            dbus_call("Click", int(cursor_x), int(cursor_y))
            continue

        # Not a tracking command — let the user run normal system commands
        # without leaving tracking ("volume up", "open files", "scroll down", …).
        # Re-transcribe the same audio with the general prompt for accuracy, then
        # route it globally (which skips the blocking modes).
        if any(
            w in cmd_lower for w in ["grid", "browser", "notes", "dictation", "labels"]
        ):
            core.speak("Say stop tracking first to use that.")
            continue
        general = (core.transcribe(audio) or "").lower().strip(".,!? ")
        if general and core.run_global_command(general) is None:
            print(f"  → ignored: {general}")
