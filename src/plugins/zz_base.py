from EchoBase.core import phrases

NAME = "base"
DESCRIPTION = "Help and exit commands"

COMMANDS = [
    "help - list all commands",
    "stop/exit/quit - exit EchoBase",
]

# Canonical spoken forms for the fuzzy near-miss recovery (main._recover).
PHRASES = ["help", "stop", "exit", "quit"]

core = None


def setup(c):
    global core
    core = c


def handle(cmd, core):
    cmd_lower = cmd.lower().strip()

    if "tracking" not in cmd_lower:
        if cmd_lower in ["stop", "exit", "quit", "goodbye", "bye"]:
            core.speak(
                phrases.farewell(getattr(core, "user_name", "")), allow_lead=False
            )
            return False  # Signal to exit
        if any(cmd_lower.endswith(x) for x in [" stop", " exit", " quit"]):
            core.speak(
                phrases.farewell(getattr(core, "user_name", "")), allow_lead=False
            )
            return False

    # Help
    if "help" in cmd_lower or "what can you do" in cmd_lower:
        show_help(core)
        return True

    return None  # Not handled


def show_help(core):
    print("\n=== Available Commands ===")
    for plugin in core.plugins:
        if hasattr(plugin, "COMMANDS"):
            print(f"\n{plugin.NAME}:")
            for cmd in plugin.COMMANDS:
                print(f"  • {cmd}")
    print()
    core.speak("Check the terminal for available commands.")
