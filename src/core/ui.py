import sys

RESET = "\x1b[0m"
DIM = "\x1b[2m"
BOLD = "\x1b[1m"
RED = "\x1b[31m"
GREEN = "\x1b[32m"
YELLOW = "\x1b[33m"
BLUE = "\x1b[34m"
MAGENTA = "\x1b[35m"
CYAN = "\x1b[36m"
GRAY = "\x1b[90m"

_USE_COLOR = sys.stdout.isatty()

TAG_WIDTH = 6
LABEL_WIDTH = 18
PANEL_WIDTH = 50

# Predefined assistant names
_DEFAULT_NAMES = ["Jarvis", "Echo", "Nova", "Atlas", "Sage"]


def c(code, text):
    return f"{code}{text}{RESET}" if _USE_COLOR else text


def clear_screen():
    print("\033[2J\033[H", end="", flush=True)


def log(tag, message, color=GRAY):
    print(f"  {c(color, tag.rjust(TAG_WIDTH))}  {message}")


def select_assistant_name():
    clear_screen()

    box_w = 46
    print()
    print("  " + c(CYAN, "╔" + "═" * box_w + "╗"))
    title = "Choose your assistant name"
    print("  " + c(CYAN, "║") + c(BOLD, title.center(box_w)) + c(CYAN, "║"))
    print("  " + c(CYAN, "╠" + "═" * box_w + "╣"))
    print("  " + c(CYAN, "║") + " " * box_w + c(CYAN, "║"))

    for i, name in enumerate(_DEFAULT_NAMES, 1):
        line = f"   [{i}]  {name}"
        print("  " + c(CYAN, "║") + line + " " * (box_w - len(line)) + c(CYAN, "║"))

    print("  " + c(CYAN, "║") + " " * box_w + c(CYAN, "║"))
    custom_line = f"   [{len(_DEFAULT_NAMES) + 1}]  Custom name..."
    print("  " + c(CYAN, "║") + custom_line + " " * (box_w - len(custom_line)) + c(CYAN, "║"))
    print("  " + c(CYAN, "║") + " " * box_w + c(CYAN, "║"))
    print("  " + c(CYAN, "╚" + "═" * box_w + "╝"))
    print()

    max_choice = len(_DEFAULT_NAMES) + 1

    while True:
        try:
            raw = input(f"  Enter choice (1-{max_choice}): ").strip()
            num = int(raw)
            if 1 <= num <= len(_DEFAULT_NAMES):
                clear_screen()
                return _DEFAULT_NAMES[num - 1]
            if num == max_choice:
                name = input("  Enter custom name: ").strip()
                if name:
                    clear_screen()
                    return name
                print("  " + c(RED, "Name cannot be empty."))
            else:
                print("  " + c(RED, f"Please enter 1-{max_choice}."))
        except ValueError:
            print("  " + c(RED, f"Please enter 1-{max_choice}."))
        except (KeyboardInterrupt, EOFError):
            clear_screen()
            return _DEFAULT_NAMES[0]


_ASCII_LOGO = r"""
__/\\\\\\\\\\\\\\\________/\\\\\\\\\__/\\\________/\\\_______/\\\\\_______/\\\\\\\\\\\\\_______/\\\\\\\\\________/\\\\\\\\\\\____/\\\\\\\\\\\\\\\_
 _\/\\\///////////______/\\\////////__\/\\\_______\/\\\_____/\\\///\\\____\/\\\/////////\\\___/\\\\\\\\\\\\\____/\\\/////////\\\_\/\\\///////////__
  _\/\\\_______________/\\\/___________\/\\\_______\/\\\___/\\\/__\///\\\__\/\\\_______\/\\\__/\\\/////////\\\__\//\\\______\///__\/\\\_____________
   _\/\\\\\\\\\\\______/\\\_____________\/\\\\\\\\\\\\\\\__/\\\______\//\\\_\/\\\\\\\\\\\\\\__\/\\\_______\/\\\___\////\\\_________\/\\\\\\\\\\\_____
    _\/\\\///////______\/\\\_____________\/\\\/////////\\\_\/\\\_______\/\\\_\/\\\/////////\\\_\/\\\\\\\\\\\\\\\______\////\\\______\/\\\///////______
     _\/\\\_____________\//\\\____________\/\\\_______\/\\\_\//\\\______/\\\__\/\\\_______\/\\\_\/\\\/////////\\\_________\////\\\___\/\\\_____________
      _\/\\\______________\///\\\__________\/\\\_______\/\\\__\///\\\__/\\\____\/\\\_______\/\\\_\/\\\_______\/\\\__/\\\______\//\\\__\/\\\_____________
       _\/\\\\\\\\\\\\\\\____\////\\\\\\\\\_\/\\\_______\/\\\____\///\\\\\/_____\/\\\\\\\\\\\\\/__\/\\\_______\/\\\_\///\\\\\\\\\\\/___\/\\\\\\\\\\\\\\\_
        _\///////////////________\/////////__\///________\///_______\/////_______\/////////////____\///________\///____\///////////_____\///////////////__
"""


def banner():
    print()
    for line in _ASCII_LOGO.strip("\n").splitlines():
        print(c(CYAN, line))
    print()
    print("  " + c(DIM, "voice control for linux"))
    print()


def step(label, value):
    print(f"  {label:<{LABEL_WIDTH}}{c(DIM, value)}")


def section(title):
    print()
    print("  " + c(DIM, title))


def ready_hint(name="Jarvis"):
    print()
    print("  " + c(DIM, f'Say "Hey {name}" then a command.  Ctrl+C to quit.'))
    print()


def panel(title, rows, color=BLUE):
    inner = PANEL_WIDTH - 2
    top = f"┌─ {title} " + "─" * (inner - len(title) - 3) + "┐"
    bottom = "└" + "─" * inner + "┘"
    print()
    print("  " + c(color, top))
    for row in rows:
        pad = inner - 2 - _visible_len(row)
        print("  " + c(color, "│") + " " + row + " " * max(pad, 0) + " " + c(color, "│"))
    print("  " + c(color, bottom))


def _visible_len(text):
    out = []
    skip = False
    for ch in text:
        if ch == "\x1b":
            skip = True
            continue
        if skip:
            if ch == "m":
                skip = False
            continue
        out.append(ch)
    return len("".join(out))
