"""Browser voice control that works with *any* browser.

Previously this drove qutebrowser exclusively via its command IPC. It now drives
whatever browser the user picked in the OOBE (``config["browser"]``) using only
portable mechanisms exposed by the GNOME Shell extension:

  * standard keyboard shortcuts (new tab Ctrl+T, close Ctrl+W, address bar
    Ctrl+L, find Ctrl+F, back Alt+Left, …) sent via the extension's ``KeyCombo``,
  * mouse-wheel ``Scroll`` at the pointer, and
  * the AT-SPI numbered-label overlay (``labels.show``) for clicking links —
    which works in Firefox/Chrome/Brave/etc. once accessibility is enabled.

So the same spoken commands behave identically across browsers.
"""

import re
import time

from EchoBase.core import config, ui
from EchoBase.plugins import labels

NAME = "browser"
DESCRIPTION = "Voice control for your chosen web browser"

COMMANDS = [
    "numbers / links - number the links, then say one to click",
    "back / forward - navigation",
    "scroll up / scroll down - scroll page",
    "top / bottom - jump to top/bottom",
    "reload - refresh page",
    "new tab / close tab - manage tabs",
    "next tab / last tab - switch tabs",
    "find [text] - search on page",
    "go to [site] - open a site",
    "search [query] - search the web",
]

PHRASES = [
    "browser",
    "new tab",
    "close tab",
    "next tab",
    "last tab",
    "reload",
    "back",
    "forward",
    "scroll up",
    "scroll down",
    "numbers",
    "find",
    "go to",
    "search",
]

core = None

# Number words for hint/tab selection (kept for tab numbers and parsing tests).
HINT_NUMBERS = {
    "zero": "0",
    "oh": "0",
    "one": "1",
    "won": "1",
    "wan": "1",
    "two": "2",
    "to": "2",
    "too": "2",
    "tu": "2",
    "three": "3",
    "tree": "3",
    "free": "3",
    "four": "4",
    "for": "4",
    "fore": "4",
    "five": "5",
    "six": "6",
    "sex": "6",
    "seven": "7",
    "eight": "8",
    "ate": "8",
    "nine": "9",
    "nein": "9",
    "0": "0",
    "1": "1",
    "2": "2",
    "3": "3",
    "4": "4",
    "5": "5",
    "6": "6",
    "7": "7",
    "8": "8",
    "9": "9",
}

BOOKMARKS = {
    "youtube": "https://youtube.com",
    "google": "https://google.com",
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
    "reddit": "https://reddit.com",
    "twitter": "https://twitter.com",
    "facebook": "https://facebook.com",
    "amazon": "https://amazon.com",
    "netflix": "https://netflix.com",
    "duckduckgo": "https://duckduckgo.com",
    "duck": "https://duckduckgo.com",
}

# Spoken triggers for the link-hint overlay (and common mishearings).
HINT_TRIGGERS = {
    "numbers",
    "number",
    "hints",
    "hint",
    "show numbers",
    "show hints",
    "links",
    "link",
    "blanks",
    "blinks",
    "lynx",
    "lings",
    "lanes",
    "licks",
    "clicks",
}


def setup(c):
    global core
    core = c


# --- Input primitives via the GNOME Shell extension --------------------------


def _ext(method, *args):
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
    result = core.host_run(cmd)
    if getattr(result, "returncode", 1) != 0:
        ui.log("error", "browser · extension not enabled", ui.RED)
        return False
    return True


def _key(combo):
    """Send a keyboard shortcut like 'ctrl+t' to the focused window."""
    ui.log("exec", f"key {combo}", ui.BLUE)
    return _ext("KeyCombo", combo)


def _press(name):
    """Tap a single named key like 'enter' / 'escape' / 'pagedown'."""
    return _ext("PressKey", name)


def _screen_center():
    result = core.host_run(
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
    if getattr(result, "returncode", 1) == 0:
        m = re.search(r"\((\d+),\s*(\d+)\)", result.stdout or "")
        if m:
            return int(m.group(1)) // 2, int(m.group(2)) // 2
    return 960, 540


def _scroll(direction, clicks=3):
    x, y = _screen_center()
    _ext("Scroll", x, y, direction, clicks)


def _navigate(url):
    """Open *url* in the current tab via the address bar (Ctrl+L, type, Enter)."""
    _key("ctrl+l")
    time.sleep(0.25)
    _press("delete")  # clear the selected address text
    time.sleep(0.05)
    core.type_text(url)
    time.sleep(0.05)
    _press("enter")


# --- Parsing helpers (browser-agnostic; covered by unit tests) ---------------


def parse_hint_numbers(cmd):
    """Extract hint digits from spoken words ('zero two' -> '02')."""
    clean = re.sub(r"[.,!?\-]", " ", cmd.lower())
    digits = [HINT_NUMBERS[w] for w in clean.split() if w in HINT_NUMBERS]
    return "".join(digits)


def looks_like_hint(cmd):
    """Whether a command looks like a short spoken number (a hint/tab index)."""
    clean = re.sub(r"[.,!?\-\s]", "", cmd.lower())
    if len(clean) > 6:
        return False
    if clean.replace("o", "0").isdigit():
        return True
    words = cmd.lower().split()
    if len(words) <= 3 and all(w.strip(".,!?") in HINT_NUMBERS for w in words):
        return True
    return False


def parse_hint_number(cmd):
    """Parse spoken numbers into a digit string ('ninety three' -> '93')."""
    NUM_WORDS = {
        "zero": "0",
        "oh": "0",
        "o": "0",
        "one": "1",
        "won": "1",
        "wan": "1",
        "two": "2",
        "to": "2",
        "too": "2",
        "tu": "2",
        "three": "3",
        "tree": "3",
        "free": "3",
        "four": "4",
        "for": "4",
        "fore": "4",
        "five": "5",
        "six": "6",
        "sex": "6",
        "seven": "7",
        "eight": "8",
        "ate": "8",
        "nine": "9",
        "nein": "9",
        "ten": "10",
        "eleven": "11",
        "twelve": "12",
        "thirteen": "13",
        "fourteen": "14",
        "fifteen": "15",
        "sixteen": "16",
        "seventeen": "17",
        "eighteen": "18",
        "nineteen": "19",
        "twenty": "2",
        "thirty": "3",
        "forty": "4",
        "fifty": "5",
        "sixty": "6",
        "seventy": "7",
        "eighty": "8",
        "ninety": "9",
    }
    result = []
    for word in re.sub(r"[.,!?\-]", " ", cmd.lower()).split():
        if word.isdigit():
            result.append(word)
        elif word in NUM_WORDS:
            result.append(NUM_WORDS[word])
    return "".join(result)


def parse_spoken_url(spoken):
    """Convert a spoken URL to a real one ('claude dot ai' -> 'https://claude.ai')."""
    url = spoken.lower().strip()
    url = url.replace(" dot ", ".")
    url = url.replace(" slash ", "/")
    url = url.replace(" colon ", ":")
    url = url.replace(" dash ", "-")
    url = url.replace(" hyphen ", "-")
    url = url.replace(" underscore ", "_")
    url = url.replace(" ", "")
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    return url


# --- Mode + command handling -------------------------------------------------


def launch_browser(core):
    """Launch the user's configured browser in the background."""
    binary = config.browser_command(getattr(core, "config", {}) or {})
    ui.log("exec", f"launch {binary}", ui.BLUE)
    core.host_run([binary], background=True)
    return binary


def handle(cmd, core):
    cmd_lower = cmd.lower().strip(".,!? ")

    # Enter browser mode (explicit).
    if cmd_lower in ["browser", "browser mode", "open browser", "launch browser"]:
        launch_browser(core)
        time.sleep(1.0)
        browser_mode(core)
        return True

    # A single browser command also drops into browser mode afterward.
    try:
        result = handle_browser_command(cmd_lower, core)
        if result:
            ui.log("info", "entering browser mode", ui.DIM)
            browser_mode(core)
            return True
    except Exception as e:
        ui.log("error", f"browser · {e}", ui.RED)
        return True

    return None


def browser_mode(core):
    """Continuous listening for browser commands."""
    if core is not None:
        core.active_mode = "browser"
    core.speak("Browser")
    ui.panel(
        "browser mode",
        [
            "active · say commands directly",
            ui.c(ui.DIM, 'leave · "exit browser"'),
        ],
        color=ui.BLUE,
    )

    try:
        while True:
            try:
                core.stream.read(
                    core.stream.get_read_available(), exception_on_overflow=False
                )
            except Exception:
                pass

            first = core.wait_for_speech(timeout=30)
            if not first:
                continue

            audio = first + core.record_until_silence()
            cmd = core.transcribe(audio)
            if not cmd:
                continue

            cmd_lower = cmd.lower().strip(".,!? ")
            ui.log("heard", cmd_lower, ui.YELLOW)

            # Exit browser mode — require an explicit phrase.
            if cmd_lower in [
                "exit browser",
                "leave browser",
                "stop browser",
                "quit browser",
                "close browser",
            ]:
                ui.log("info", "leaving browser mode", ui.DIM)
                return

            # Grid triggers — hand off to grid mode.
            grid_triggers = {"grid", "grit", "grip", "mouse", "pointer", "cursor"}
            if any(w in cmd_lower for w in grid_triggers):
                ui.log("info", "leaving browser mode for grid", ui.DIM)
                if core is not None:
                    core.active_mode = None
                core.route_command(cmd_lower)
                return

            if not handle_browser_command(cmd_lower, core):
                ui.log("info", f"unknown · {cmd_lower}", ui.DIM)
    finally:
        if core is not None:
            core.active_mode = None


def handle_browser_command(cmd_lower, core):
    # --- Link hints (AT-SPI numbered labels; any browser) ---
    if cmd_lower in HINT_TRIGGERS:
        labels.show(core)
        return True

    # --- Navigation ---
    if cmd_lower in ["back", "go back", "previous page"]:
        _key("alt+left")
        return True
    if cmd_lower in ["forward", "go forward", "next page"]:
        _key("alt+right")
        return True
    if cmd_lower in ["reload", "refresh", "reload page"]:
        _key("ctrl+r")
        return True
    if cmd_lower in ["stop", "stop loading"]:
        _press("escape")
        return True

    # --- Scrolling ---
    if cmd_lower in ["scroll down", "down"]:
        _scroll("down")
        return True
    if cmd_lower in ["scroll up", "up"]:
        _scroll("up")
        return True
    if "page" in cmd_lower and "down" in cmd_lower:
        _press("pagedown")
        return True
    if "page" in cmd_lower and "up" in cmd_lower:
        _press("pageup")
        return True
    if cmd_lower in ["top", "go to top", "scroll to top"]:
        _key("ctrl+home")
        return True
    if cmd_lower in ["bottom", "go to bottom", "scroll to bottom"]:
        _key("ctrl+end")
        return True

    # --- Tabs ---
    if cmd_lower.startswith("tab "):
        tab_num = parse_hint_number(cmd_lower.replace("tab ", "").strip())
        if tab_num and tab_num.isdigit() and 1 <= int(tab_num) <= 8:
            _key(f"ctrl+{tab_num}")
            return True
    if cmd_lower in ["new tab", "open tab"]:
        _key("ctrl+t")
        return True
    if cmd_lower in ["close tab", "close this tab"]:
        _key("ctrl+w")
        return True
    if cmd_lower in ["next tab", "tab right"]:
        _key("ctrl+tab")
        return True
    if cmd_lower in ["last tab", "previous tab", "tab left"]:
        _key("ctrl+shift+tab")
        return True
    if cmd_lower in ["undo tab", "restore tab", "reopen tab"]:
        _key("ctrl+shift+t")
        return True

    # --- Find ---
    if cmd_lower.startswith("find "):
        query = cmd_lower.replace("find ", "", 1).strip()
        if query in ("next", "next match"):
            _key("ctrl+g")
            return True
        if query in ("previous", "previous match", "back"):
            _key("ctrl+shift+g")
            return True
        if query:
            _key("ctrl+f")
            time.sleep(0.2)
            core.type_text(query)
            return True
    if cmd_lower in ["find next", "next match"]:
        _key("ctrl+g")
        return True
    if cmd_lower in ["find previous", "previous match"]:
        _key("ctrl+shift+g")
        return True

    # --- Escape ---
    if cmd_lower in ["escape", "cancel", "nevermind"]:
        _press("escape")
        return True

    # --- Bookmark current page ---
    if "bookmark this" in cmd_lower or "save this" in cmd_lower:
        _key("ctrl+d")
        core.speak("Opening the bookmark dialog.")
        return True

    # --- Go to / open a site ---
    if cmd_lower.startswith("go to ") or cmd_lower.startswith("open "):
        target = cmd_lower.replace("go to ", "").replace("open ", "").strip()

        for site, url in BOOKMARKS.items():
            if site == target:
                _navigate(url)
                core.speak(f"Opening {site}.")
                return True

        if "dot" in target or "." in target:
            url = parse_spoken_url(target)
            _navigate(url)
            core.speak(f"Opening {url}.")
            return True

        # "go to X" with no domain -> search for X; bare "open X" is left for the
        # apps plugin (e.g. "open files").
        if cmd_lower.startswith("go to ") and target:
            _navigate(f"https://duckduckgo.com/?q={target.replace(' ', '+')}")
            core.speak(f"Searching for {target}.")
            return True
        return None

    # --- Search ---
    if cmd_lower.startswith("search "):
        query = cmd_lower.replace("search for ", "").replace("search ", "").strip()
        if query:
            _navigate(f"https://duckduckgo.com/?q={query.replace(' ', '+')}")
            core.speak(f"Searching for {query}.")
            return True

    return None
