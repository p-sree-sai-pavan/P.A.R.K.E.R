"""
interface.py — Parker AI Terminal Interface
Production-grade Rich CLI with clean, minimal aesthetic.
"""
import os
import sys
import json
import warnings
from datetime import datetime

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.status import Status
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich.theme import Theme
from rich.columns import Columns
from rich.align import Align
from rich.padding import Padding
from rich.syntax import Syntax
from rich.live import Live
from rich.layout import Layout
from rich import box

warnings.filterwarnings("ignore", message=".*Deserializing unregistered type.*")


# ════════════════════════════════════════════════════════════════════════════════
# Theme
# ════════════════════════════════════════════════════════════════════════════════

PARKER_THEME = Theme({
    # Core brand
    "pk":          "bold #D97757",
    "pk.dim":      "#9B4E30",
    "pk.soft":     "#E8916E",
    # Gold / accent
    "ac":          "#D9A05B",
    "ac.dim":      "#8F6125",
    # Neutral text
    "tx":          "#E5E5E5",
    "tx.dim":      "#737373",
    "tx.muted":    "#404040",
    # Semantic
    "ok":          "#4ADE80",
    "ok.dim":      "#166534",
    "warn":        "#FBBF24",
    "warn.dim":    "#78350F",
    "err":         "#F87171",
    "err.dim":     "#7F1D1D",
    "info":        "#60A5FA",
    # Borders
    "border":      "#262626",
    "border.hi":   "#404040",
})

console = Console(theme=PARKER_THEME, highlight=False)


# ════════════════════════════════════════════════════════════════════════════════
# Banner
# ════════════════════════════════════════════════════════════════════════════════

_BANNER_LINES = [
    (" ▄▄▄·  ▄▄▄· ▄▄▄  ▄ •▄ ▄▄▄ .▄▄▄ .", "pk"),
    (" █▀▀█ ▐█ ▀█ ▀▄ █·█▌▄▌▪▀▄.▀·▀▄.▀·", "pk.soft"),
    (" █▄▄█▌▄█▀▀█ ▐▀▀▄ ▐▀▀▄·▐▀▀▪▄▐▀▀▪▄", "tx"),
    (" ▀▀▀ ·▀▀ ▀▀ ·  · ·▀  ▀▀▀▀ ·▀▀▀▀ ", "tx.dim"),
]


def print_parker_banner():
    """Compact, clean banner with a single status line beneath."""
    console.print()
    for line, style in _BANNER_LINES:
        console.print(f"  [bold {style}]{line}[/]")

    console.print()

    # Single status bar under the art
    now = datetime.now().strftime("%a %b %d  %H:%M")
    parts = Text()
    parts.append("  ")
    parts.append("● ", style="pk")
    parts.append("memory active", style="tx.dim")
    parts.append("    ", style="")
    parts.append("◆ ", style="ac")
    parts.append("groq  ollama  pgvector", style="tx.dim")
    parts.append("    ", style="")
    parts.append("◇ ", style="tx.dim")
    parts.append(now, style="tx.dim")

    console.print(parts)
    console.print()
    console.print(Rule(style="border"))
    console.print()


# ════════════════════════════════════════════════════════════════════════════════
# Status / info bar
# ════════════════════════════════════════════════════════════════════════════════

def print_status_bar(model: str = "", memory: str = "Active", mode: str = "text"):
    """
    One-line status bar: model · memory state · input mode.
    Printed once after the banner; refreshed when mode changes.
    """
    model_short = model.split("/")[-1] if model else "—"

    bar = Text("  ")
    bar.append("model ", style="tx.dim")
    bar.append(model_short, style="ac")
    bar.append("  ·  ", style="tx.muted")
    bar.append("memory ", style="tx.dim")
    bar.append(memory.lower(), style="ok" if memory.lower() == "active" else "warn")
    bar.append("  ·  ", style="tx.muted")
    bar.append("mode ", style="tx.dim")
    bar.append(mode, style="pk" if mode == "voice" else "tx")

    console.print(bar)
    console.print()


# ════════════════════════════════════════════════════════════════════════════════
# Message rendering
# ════════════════════════════════════════════════════════════════════════════════

def print_user(message: str):
    """Print the user's message — right-aligned feel with a subtle prefix."""
    ts = datetime.now().strftime("%H:%M")

    header = Text("  ")
    header.append("you", style="bold tx")
    header.append(f"  {ts}", style="tx.muted")
    console.print(header)

    # Message body — indent, plain white
    for line in message.splitlines():
        console.print(f"  [tx]{line}[/]")
    console.print()


def print_parker(message: str, mem_hint: str = ""):
    """
    Print Parker's response.

    mem_hint: optional short string shown in the header, e.g.
              "↑ profile  facts  2 episodes"
    """
    ts = datetime.now().strftime("%H:%M")

    # Header row
    header = Text("  ")
    header.append("parker", style="pk")
    header.append(f"  {ts}", style="tx.muted")
    if mem_hint:
        header.append(f"  ·  {mem_hint}", style="tx.dim")

    console.print(header)

    # Left-border accent panel
    # Render the markdown inside a panel with a left rule to visually anchor it
    md = Markdown(message, code_theme="dracula", inline_code_lexer="python")
    panel = Panel(
        md,
        border_style="pk.dim",
        box=box.SIMPLE,          # clean — just a top/bottom rule
        padding=(0, 2),
    )
    console.print(Padding(panel, (0, 0, 0, 2)))  # indent entire block 2 chars
    console.print()


def print_memory_note(note: str):
    """
    Show a subtle inline memory activity line — e.g. what was retrieved or saved.
    Not printed in normal use; hook in from trigger/retrieve nodes if desired.
    """
    line = Text("  ")
    line.append("↑ ", style="pk.dim")
    line.append(note, style="tx.dim")
    console.print(line)


# ════════════════════════════════════════════════════════════════════════════════
# System / status messages
# ════════════════════════════════════════════════════════════════════════════════

def print_system(message: str):
    line = Text("  ")
    line.append("· ", style="tx.muted")
    line.append(message, style="tx.dim")
    console.print(line)


def print_success(message: str):
    line = Text("  ")
    line.append("✓ ", style="ok")
    line.append(message, style="tx.dim")
    console.print(line)


def print_warning(message: str):
    line = Text("  ")
    line.append("⚠ ", style="warn")
    line.append(message, style="warn")
    console.print(line)


def print_error(message: str):
    panel = Panel(
        Text(message, style="err"),
        border_style="err.dim",
        box=box.SIMPLE,
        padding=(0, 2),
        title=Text(" error ", style="bold err"),
        title_align="left",
    )
    console.print(Padding(panel, (0, 0, 0, 2)))


def print_header(title: str, subtitle: str = ""):
    console.print()
    h = Text("  ")
    h.append(title, style="bold tx")
    if subtitle:
        h.append(f"  {subtitle}", style="tx.dim")
    console.print(h)
    console.print(f"  [border.hi]{'─' * 40}[/]")


# ════════════════════════════════════════════════════════════════════════════════
# Commands table
# ════════════════════════════════════════════════════════════════════════════════

def print_commands_table():
    """Clean two-column command reference."""
    COMMANDS = [
        ("t / v",        "switch text ↔ voice"),
        ("/clear",       "clear screen"),
        ("/profile",     "show memory profile"),
        ("/facts",       "list stored facts"),
        ("/projects",    "list active projects"),
        ("exit",         "save & quit"),
    ]

    t = Table(
        show_header=False,
        show_edge=False,
        box=None,
        padding=(0, 3, 0, 0),
    )
    t.add_column(style="ac", min_width=12, no_wrap=True)
    t.add_column(style="tx.dim")

    for cmd, desc in COMMANDS:
        t.add_row(cmd, desc)

    console.print(Padding(t, (0, 0, 1, 4)))


# ════════════════════════════════════════════════════════════════════════════════
# Profile panel
# ════════════════════════════════════════════════════════════════════════════════

def print_profile_panel(profile: dict):
    if not profile:
        print_system("No profile saved yet.")
        return

    t = Table(
        show_header=False,
        show_edge=False,
        box=None,
        padding=(0, 3, 0, 0),
    )
    t.add_column(style="tx.dim", min_width=18, no_wrap=True)
    t.add_column(style="tx")

    for key, value in profile.items():
        label = key.replace("_", " ")
        val_str = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        t.add_row(label, val_str)

    panel = Panel(
        Padding(t, (0, 0, 0, 1)),
        title=Text(" profile ", style="bold pk"),
        title_align="left",
        border_style="border.hi",
        box=box.SIMPLE,
        padding=(1, 2),
    )
    console.print()
    console.print(Padding(panel, (0, 0, 0, 2)))
    console.print()


def print_facts_panel(facts: list):
    """Display stored facts by importance tier."""
    if not facts:
        print_system("No facts stored yet.")
        return

    importance_style = {
        "critical": "bold err",
        "high":     "warn",
        "normal":   "tx",
        "low":      "tx.dim",
    }
    importance_label = {
        "critical": "●",
        "high":     "◆",
        "normal":   "◇",
        "low":      "·",
    }

    t = Table(
        show_header=False,
        show_edge=False,
        box=None,
        padding=(0, 3, 0, 0),
    )
    t.add_column(width=2, no_wrap=True)
    t.add_column(style="tx.dim", min_width=14, no_wrap=True)
    t.add_column(style="tx")

    for item in sorted(facts, key=lambda i: ["critical","high","normal","low"].index(i.get("importance","normal"))):
        imp = item.get("importance", "normal")
        icon = Text(importance_label.get(imp, "·"), style=importance_style.get(imp, "tx.dim"))
        key_text = Text(item.get("key", "").replace("_", " "), style="tx.dim")
        val_text = Text(item.get("content", ""), style="tx")
        t.add_row(icon, key_text, val_text)

    panel = Panel(
        Padding(t, (0, 0, 0, 1)),
        title=Text(" facts ", style="bold pk"),
        title_align="left",
        border_style="border.hi",
        box=box.SIMPLE,
        padding=(1, 2),
    )
    console.print()
    console.print(Padding(panel, (0, 0, 0, 2)))
    console.print()


def print_projects_panel(projects: list):
    """Display active projects with stack + status."""
    if not projects:
        print_system("No projects stored yet.")
        return

    status_style = {
        "active":    "ok",
        "paused":    "warn",
        "completed": "tx.dim",
        "abandoned": "tx.muted",
    }

    t = Table(
        show_header=False,
        show_edge=False,
        box=None,
        padding=(0, 3, 0, 0),
    )
    t.add_column(style="bold tx", min_width=18)
    t.add_column(min_width=10)
    t.add_column(style="tx.dim")

    for p in projects:
        v      = p.value if hasattr(p, "value") else p
        name   = v.get("name", "unknown")
        status = v.get("status", "active")
        stack  = ", ".join(v.get("stack", []))
        summary = v.get("summary", "")

        status_text = Text(status, style=status_style.get(status, "tx.dim"))
        t.add_row(name, status_text, stack or summary)

    panel = Panel(
        Padding(t, (0, 0, 0, 1)),
        title=Text(" projects ", style="bold pk"),
        title_align="left",
        border_style="border.hi",
        box=box.SIMPLE,
        padding=(1, 2),
    )
    console.print()
    console.print(Padding(panel, (0, 0, 0, 2)))
    console.print()


# ════════════════════════════════════════════════════════════════════════════════
# Spinner
# ════════════════════════════════════════════════════════════════════════════════

def get_spinner(message: str = "thinking") -> Status:
    return console.status(
        f"  [tx.dim]{message}[/]",
        spinner="dots",
        spinner_style="pk",
    )


# ════════════════════════════════════════════════════════════════════════════════
# Input prompt
# ════════════════════════════════════════════════════════════════════════════════

def get_user_prompt(mode: str = "text") -> str:
    if mode == "voice":
        return "\n  [pk]❯[/] [tx.dim]press enter to speak[/]  "
    return "\n  [pk]❯[/] "


# ════════════════════════════════════════════════════════════════════════════════
# Dividers
# ════════════════════════════════════════════════════════════════════════════════

def print_divider(label: str = ""):
    if label:
        console.print(Rule(label, style="border", align="left"))
    else:
        console.print(Rule(style="border"))


def print_session_divider(session_id: str = ""):
    """Thin labeled rule between sessions."""
    label = f" {session_id} " if session_id else " new session "
    console.print()
    console.print(Rule(label, style="tx.muted", align="center"))
    console.print()


# ════════════════════════════════════════════════════════════════════════════════
# Mode switch notification
# ════════════════════════════════════════════════════════════════════════════════

def print_mode_switch(new_mode: str):
    icon = "🎙" if new_mode == "voice" else "⌨"
    line = Text(f"  {icon}  switched to ", style="tx.dim")
    line.append(new_mode, style="pk" if new_mode == "voice" else "tx")
    line.append(" mode", style="tx.dim")
    console.print()
    console.print(line)
    console.print()


# ════════════════════════════════════════════════════════════════════════════════
# Goodbye
# ════════════════════════════════════════════════════════════════════════════════

def print_goodbye():
    console.print()
    msg = Text("  ")
    msg.append("parker", style="pk")
    msg.append(" going offline — see you soon", style="tx.dim")
    console.print(msg)
    console.print()


# ════════════════════════════════════════════════════════════════════════════════
# Setup wizard (first-run .env creation)
# ════════════════════════════════════════════════════════════════════════════════

def setup_environment():
    if os.path.exists(".env"):
        return

    console.print()
    console.print(Rule(style="border"))
    console.print()

    h = Text("  ")
    h.append("welcome to parker", style="bold pk")
    console.print(h)
    console.print(f"  [tx.dim]first-time setup — three quick steps[/]")
    console.print()

    # Step 1
    console.print("  [ac]01[/] [tx.dim]what should parker call you?[/]")
    name = Prompt.ask("  [pk]❯[/]")

    # Step 2
    console.print()
    console.print("  [ac]02[/] [tx.dim]groq api key  ·  get one free at console.groq.com[/]")
    api_key = Prompt.ask("  [pk]❯[/]", password=True)

    # Step 3
    console.print()
    console.print("  [ac]03[/] [tx.dim]chat model[/]")

    choices_table = Table(show_header=False, show_edge=False, box=None, padding=(0, 3, 0, 4))
    choices_table.add_column(style="ac", width=3)
    choices_table.add_column(style="tx")
    choices_table.add_column(style="tx.dim")
    choices_table.add_row("1", "llama-3.3-70b-versatile", "recommended")
    choices_table.add_row("2", "mixtral-8x7b-32768",      "longer context")
    choices_table.add_row("3", "gemma2-9b-it",            "lightweight")
    console.print(choices_table)
    console.print()

    choice = Prompt.ask("  [pk]❯[/]", choices=["1", "2", "3"], default="1")
    model_map = {"1": "llama-3.3-70b-versatile", "2": "mixtral-8x7b-32768", "3": "gemma2-9b-it"}
    selected_model = model_map[choice]

    with open(".env", "w") as f:
        f.write(f"GROQ_API_KEY={api_key}\nUSER_NAME={name}\nCHAT_LLM_MODEL={selected_model}\n")

    console.print()
    print_success(f"saved  ·  model: {selected_model}")
    console.print()
    console.print(Rule(style="border"))


# ════════════════════════════════════════════════════════════════════════════════
# Screen
# ════════════════════════════════════════════════════════════════════════════════

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")