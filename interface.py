"""
interface.py — Parker AI Terminal Interface
Production-grade Rich CLI with clean, minimal aesthetic.
"""
import os
import sys
import json
import warnings
from datetime import datetime
import threading
import time

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

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _supports_unicode_output() -> bool:
    encoding = (getattr(sys.stdout, "encoding", None) or "").lower()
    return "utf" in encoding or "65001" in encoding


_USE_UNICODE = _supports_unicode_output()


def _glyph(unicode_text: str, ascii_text: str) -> str:
    return unicode_text if _USE_UNICODE else ascii_text


STATUS_SEP = _glyph("  ·  ", "  |  ")
STATUS_OK = _glyph("✓ ", "[OK] ")
STATUS_WARN = _glyph("⚠ ", "[!] ")
MODE_VOICE = _glyph("🎙", "mic")
MODE_TEXT = _glyph("⌨", "kbd")
PLAIN_DASH = _glyph("—", "-")
PROMPT_ARROW = _glyph("❯", ">")
BANNER_MEMORY = _glyph("● ", "* ")
BANNER_STACK = _glyph("◆ ", "+ ")
BANNER_CLOCK = _glyph("◇ ", "- ")


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
    "ac.bold":     "bold #D9A05B",
    # Neutral text
    "tx":          "#E5E5E5",
    "tx.bold":     "bold #E5E5E5",
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

if _USE_UNICODE:
    _BANNER_LINES = [
        ("    ██████╗  █████╗ ██████╗ ██╗  ██╗███████╗██████╗ ", "pk"),
        ("    ██╔══██╗██╔══██╗██╔══██╗██║ ██╔╝██╔════╝██╔══██╗", "pk.soft"),
        ("    ██████╔╝███████║██████╔╝█████╔╝ █████╗  ██████╔╝", "tx"),
        ("    ██╔═══╝ ██╔══██║██╔══██╗██╔═██╗ ██╔══╝  ██╔══██╗", "tx.dim"),
        ("    ██║     ██║  ██║██║  ██║██║  ██╗███████╗██║  ██║", "tx.dim"),
        ("    ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝", "tx.dim"), 
    ]
else:
    _BANNER_LINES = [
        (" _____        _____  _  ________ _____  ", "pk"),
        (" |  __ \ /\   |  __ \| |/ /  ____|  __ \ ", "pk.soft"),
        (" | |__) /  \  | |__) | ' /| |__  | |__) |", "tx"),
        (" |  ___/ /\ \ |  _  /|  < |  __| |  _  / ", "tx.dim"),
        (" | |  / ____ \| | \ \| . \| |____| | \ \ ", "tx.dim"),
        (" |_| /_/    \_\_|  \_\_|\_\______|_|  \_\ ", "tx.dim"),   
    ]


_token_lock = threading.Lock()
_token_state = {
    "prompt":     0,
    "completion": 0,
    "total":      0,
    "window_start": time.time(),
    "TPM_LIMIT":  6000,  # free tier llama-3.3-70b
}

def update_token_usage(prompt_tokens: int, completion_tokens: int):
    with _token_lock:
        now = time.time()
        if now - _token_state["window_start"] > 60:
            _token_state["prompt"]     = 0
            _token_state["completion"] = 0
            _token_state["total"]      = 0
            _token_state["window_start"] = now
        _token_state["prompt"]     += prompt_tokens
        _token_state["completion"] += completion_tokens
        _token_state["total"]      += prompt_tokens + completion_tokens

def get_token_usage() -> dict:
    with _token_lock:
        limit = _token_state["TPM_LIMIT"]
        used  = _token_state["total"]
        return {
            "used":      used,
            "limit":     limit,
            "remaining": max(0, limit - used),
            "pct":       min(100, int(used / limit * 100)),
        }

def print_parker_banner():
    """Compact, clean banner with a single status line beneath."""
    console.print()
    for line, style in _BANNER_LINES:
        console.print(f"  [bold][{style}]{line}[/][/]")

    console.print()

    # Single status bar under the art
    now = datetime.now().strftime("%a %b %d  %H:%M")
    parts = Text()
    parts.append("  ")
    parts.append(BANNER_MEMORY, style="pk")
    parts.append("memory active", style="tx.dim")
    parts.append("    ", style="")
    parts.append(BANNER_STACK, style="ac")
    parts.append("groq  ollama  pgvector", style="tx.dim")
    parts.append("    ", style="")
    parts.append(BANNER_CLOCK, style="tx.dim")
    parts.append(now, style="tx.dim")

    console.print(parts)
    console.print()
    console.print(Rule(style="border"))
    console.print()


# ════════════════════════════════════════════════════════════════════════════════
# Status / info bar
# ════════════════════════════════════════════════════════════════════════════════

def print_status_bar(model: str = "", memory: str = "Active", mode: str = "text"):
    usage = get_token_usage()
    remaining = usage["remaining"]
    pct       = usage["pct"]

    # Color based on usage
    token_style = "ok" if pct < 60 else "warn" if pct < 85 else "err"

    bar = Text("  ")
    bar.append("model ", style="tx.dim")
    bar.append(model.split("/")[-1] if model else "—", style="ac")
    bar.append(STATUS_SEP, style="tx.muted")
    bar.append("memory ", style="tx.dim")
    bar.append(memory.lower(), style="ok" if memory.lower() == "active" else "warn")
    bar.append(STATUS_SEP, style="tx.muted")
    bar.append("tokens ", style="tx.dim")
    bar.append(f"{remaining:,} left", style=token_style)
    bar.append(STATUS_SEP, style="tx.muted")
    bar.append("mode ", style="tx.dim")
    bar.append(mode, style="pk" if mode == "voice" else "tx")

    console.print(bar)
    console.print()


def print_telemetry_dashboard(telemetry: dict):
    """
    Prints a beautiful system status board containing telemetry.
    """
    t = Table(
        show_header=False,
        show_edge=False,
        box=None,
        padding=(0, 2, 0, 0),
    )
    t.add_column(style="ac", min_width=15, no_wrap=True)
    t.add_column(style="tx")
    
    # Active Window
    window = telemetry.get("active_window", "Unknown")
    t.add_row("focused app", f"[tx.bold]{window}[/]")
    
    # Git status
    git_status = telemetry.get("git_status", "Clean")
    git_color = "ok" if "clean" in git_status.lower() else "warn" if "not a git" not in git_status.lower() else "tx.dim"
    
    # Show first few lines of git status
    git_lines = git_status.splitlines()
    if len(git_lines) > 3:
        git_summary = "\n".join(git_lines[:3]) + "\n..."
    else:
        git_summary = git_status
    t.add_row("workspace git", f"[{git_color}]{git_summary}[/]")
    
    # Recent files
    recent = telemetry.get("recent_files", [])
    if recent:
        files_str = "\n".join(f"- {f}" for f in recent[:5])
        if len(recent) > 5:
            files_str += "\n..."
        t.add_row("active files", files_str)
    else:
        t.add_row("active files", "[tx.dim]no modifications (last 2h)[/]")
        
    panel = Panel(
        Padding(t, (0, 1, 0, 1)),
        title="[bold pk] telemetry diagnostics [/]",
        title_align="left",
        border_style="border.hi",
        box=box.ROUNDED,
        padding=(1, 2),
    )
    console.print(Padding(panel, (0, 4, 0, 4)))
    console.print()


# ════════════════════════════════════════════════════════════════════════════════
# Message rendering
# ════════════════════════════════════════════════════════════════════════════════

def print_user(message: str):
    """Print the user's message in a clean, gold-bordered panel."""
    ts = datetime.now().strftime("%H:%M:%S")
    from config import USER_NAME
    
    panel = Panel(
        Text(message, style="tx"),
        border_style="ac.dim",
        box=box.ROUNDED,
        padding=(0, 2),
        title=f"[bold ac] {USER_NAME.lower()} [/]",
        title_align="right",
        subtitle=f"[tx.dim] {ts} [/]",
        subtitle_align="right",
    )
    console.print(Padding(panel, (0, 4, 0, 4)))


def print_parker(message: str, mem_hint: str = ""):
    """Print Parker's response inside a beautiful rounded panel."""
    ts = datetime.now().strftime("%H:%M:%S")
    
    md = Markdown(message, code_theme="dracula", inline_code_lexer="python")
    
    subtitle_str = f"[tx.dim] {ts} [/]"
    if mem_hint:
        subtitle_str = f"[tx.dim] {mem_hint} • {ts} [/]"
        
    panel = Panel(
        md,
        border_style="pk",
        box=box.ROUNDED,
        padding=(1, 2),
        title="[bold pk] parker [/]",
        title_align="left",
        subtitle=subtitle_str,
        subtitle_align="left"
    )
    console.print(Padding(panel, (0, 4, 0, 4)))


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
        box=box.ROUNDED,
        padding=(0, 2),
        title=Text(" error ", style="bold #F87171"),
        title_align="left",
    )
    console.print(Padding(panel, (0, 0, 0, 2)))


def print_header(title: str, subtitle: str = ""):
    console.print()
    h = Text("  ")
    h.append(title, style="tx.bold")
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
        ("t / v",          "switch text ↔ voice"),
        ("/clear",         "clear screen"),
        ("/telemetry",     "display active telemetry status"),
        ("/import <path>", "import data from JSON or TXT file"),
        ("/profile",       "show memory profile"),
        ("/facts",         "list stored facts"),
        ("/projects",      "list active projects"),
        ("/tasks",         "list pending tasks"),
        ("/patterns",      "list observed patterns & habits"),
        ("exit",           "save & quit"),
    ]

    t = Table(
        show_header=False,
        show_edge=False,
        box=None,
        padding=(0, 3, 0, 0),
    )
    t.add_column(style="ac", min_width=18, no_wrap=True)
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
        title=Text(" profile ", style="pk"),
        title_align="left",
        border_style="border.hi",
        box=box.ROUNDED,
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
        "critical": "bold #F87171",
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
        title=Text(" facts ", style="pk"),
        title_align="left",
        border_style="border.hi",
        box=box.ROUNDED,
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
    t.add_column(style="tx.bold", min_width=18)
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
        title=Text(" projects ", style="pk"),
        title_align="left",
        border_style="border.hi",
        box=box.ROUNDED,
        padding=(1, 2),
    )
    console.print()
    console.print(Padding(panel, (0, 0, 0, 2)))
    console.print()


def print_tasks_panel(tasks: list):
    """Display pending tasks and reminders."""
    if not tasks:
        print_system("No active tasks catalogued.")
        return

    priority_style = {
        "urgent": "bold #F87171",
        "high":     "warn",
        "normal":   "tx",
        "low":      "tx.dim",
    }
    priority_label = {
        "urgent": "🔴",
        "high":     "🔶",
        "normal":   "🔹",
        "low":      "▫️",
    }

    t = Table(
        show_header=False,
        show_edge=False,
        box=None,
        padding=(0, 3, 0, 0),
    )
    t.add_column(width=3, no_wrap=True)
    t.add_column(style="tx.bold", min_width=18)
    t.add_column(style="tx")
    t.add_column(style="tx.dim", justify="right")

    priority_order = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
    sorted_tasks = sorted(
        tasks,
        key=lambda i: (
            priority_order.get(i.value.get("priority", "normal"), 2),
            i.value.get("due") or "9999-12-31"
        )
    )

    for item in sorted_tasks:
        v = item.value
        pri = v.get("priority", "normal")
        icon = Text(priority_label.get(pri, "🔹"), style=priority_style.get(pri, "tx"))
        
        name_str = item.key.replace("_", " ")
        content_str = v.get("content", "")
        
        due = v.get("due")
        cond = v.get("condition")
        due_str = ""
        if due:
            due_str = f"due: {due}"
        if cond and cond != "none":
            due_str = f"trigger: {cond}" if not due_str else f"{due_str} ({cond})"

        t.add_row(icon, name_str, content_str, due_str)

    panel = Panel(
        Padding(t, (0, 0, 0, 1)),
        title=Text(" tasks & reminders ", style="pk"),
        title_align="left",
        border_style="border.hi",
        box=box.ROUNDED,
        padding=(1, 2),
    )
    console.print()
    console.print(Padding(panel, (0, 0, 0, 2)))
    console.print()


def print_patterns_panel(patterns: list):
    """Display observed behavioral patterns and habits."""
    if not patterns:
        print_system("No behavioral patterns observed yet.")
        return

    t = Table(
        show_header=False,
        show_edge=False,
        box=None,
        padding=(0, 3, 0, 0),
    )
    t.add_column(width=3, no_wrap=True)
    t.add_column(style="tx")

    for pattern in patterns:
        t.add_row(Text("▪", style="ac"), Text(pattern))

    panel = Panel(
        Padding(t, (0, 0, 0, 1)),
        title=Text(" observed patterns & habits ", style="pk"),
        title_align="left",
        border_style="border.hi",
        box=box.ROUNDED,
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
    now_str = datetime.now().strftime("%H:%M:%S")
    from config import USER_NAME
    mode_str = "[bold pk]VOICE[/]" if mode == "voice" else "[bold ac]TEXT[/]"
    
    prompt = (
        f"\n[border]┌───[/] [bold pk]PARKER[/] [border]─[/] [tx.dim]user:[/] [tx.bold]{USER_NAME.lower()}[/] "
        f"[border]─[/] [tx.dim]mode:[/] {mode_str} [border]─[/] [tx.dim]{now_str}[/]\n"
    )
    if mode == "voice":
        prompt += f"[border]└──[/] [pk]🎙 {PROMPT_ARROW}[/] [tx.dim](press Enter to speak, speak to interrupt)[/] "
    else:
        prompt += f"[border]└──[/] [ac]⌨ {PROMPT_ARROW}[/] "
    return prompt


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
    icon = MODE_VOICE if new_mode == "voice" else MODE_TEXT
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
    msg.append(f" going offline {PLAIN_DASH} see you soon", style="tx.dim")
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
    h.append("welcome to parker", style="pk")
    console.print(h)
    console.print(f"  [tx.dim]first-time setup {PLAIN_DASH} three quick steps[/]")
    console.print()

    # Step 1
    console.print("  [ac]01[/] [tx.dim]what should parker call you?[/]")
    name = Prompt.ask(f"  [pk]{PROMPT_ARROW}[/]")

    # Step 2
    console.print()
    console.print("  [ac]02[/] [tx.dim]groq api key  ·  get one free at console.groq.com[/]")
    api_key = Prompt.ask(f"  [pk]{PROMPT_ARROW}[/]", password=True)

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

    choice = Prompt.ask(f"  [pk]{PROMPT_ARROW}[/]", choices=["1", "2", "3"], default="1")
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
