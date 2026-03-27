import os
import sys
import warnings
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
from rich import box

# Suppress annoying LangGraph MsgPack warnings
warnings.filterwarnings("ignore", message=".*Deserializing unregistered type.*")

# ═══════════════════════════════════════════════════════════════════════════════
# Claude Elegance Color Palette — "Claude Theme"
# ═══════════════════════════════════════════════════════════════════════════════
#   Primary   : #D97757  (Claude Peach)   — Parker branding, AI responses
#   Secondary : #E5E5E5  (Soft White)         — User input, interactive elements
#   Tertiary  : #D9A05B  (Muted Gold)   — Warnings, highlights, accents
#   Neutral   : #121212  (Dark)         — Background context

PARKER_THEME = Theme({
    "parker":        "bold #D97757",       # Neon green — Parker's voice
    "parker.dim":    "#C56749",            # Dimmer green — secondary parker text
    "user":          "bold #E5E5E5",       # Soft White — user elements
    "user.dim":      "#A3A3A3",            # Dimmer cyan
    "accent":        "bold #D9A05B",       # Amber — highlights
    "accent.dim":    "#C88A44",            # Dimmer amber
    "system":        "dim #E5E5E5",        # System messages
    "success":       "bold #D97757",       # Success states
    "error":         "bold #FF1744",       # Error red
    "error.dim":     "#D50000",
    "warning":       "bold #D9A05B",       # Warning amber
    "muted":         "dim #666666",        # Muted text
    "separator":     "#D97757",            # Separators
    "badge.green":   "bold #121212 on #D97757",   # Green badge
    "badge.cyan":    "bold #121212 on #E5E5E5",   # Soft White badge
    "badge.amber":   "bold #121212 on #D9A05B",   # Amber badge
    "badge.red":     "bold white on #FF1744",      # Red badge
})

console = Console(theme=PARKER_THEME)


# ═══════════════════════════════════════════════════════════════════════════════
# Banner & Branding
# ═══════════════════════════════════════════════════════════════════════════════

def print_parker_banner():
    """Display the premium Parker AI banner with cyberpunk aesthetic."""
    
    banner_art = """
[#D97757]  ██████╗   █████╗  ██████╗  ██╗  ██╗ ███████╗ ██████╗[/#D97757]
[#D97757]  ██╔══██╗ ██╔══██╗ ██╔══██╗ ██║ ██╔╝ ██╔════╝ ██╔══██╗[/#D97757]
[#E5E5E5]  ██████╔╝ ███████║ ██████╔╝ █████╔╝  █████╗   ██████╔╝[/#E5E5E5]
[#E5E5E5]  ██╔═══╝  ██╔══██║ ██╔══██╗ ██╔═██╗  ██╔══╝   ██╔══██╗[/#E5E5E5]
[#D9A05B]  ██║      ██║  ██║ ██║  ██║ ██║  ██╗ ███████╗ ██║  ██║[/#D9A05B]
[#D9A05B]  ╚═╝      ╚═╝  ╚═╝ ╚═╝  ╚═╝ ╚═╝  ╚═╝ ╚══════╝ ╚═╝  ╚═╝[/#D9A05B]"""

    subtitle_text = Text()
    subtitle_text.append("  ✦ ", style="#D9A05B")
    subtitle_text.append("Personal AI with Persistent Memory", style="#E5E5E5")
    subtitle_text.append(" ✦  ", style="#D9A05B")
    
    panel = Panel(
        Align.center(Text.from_markup(banner_art)),
        border_style="#D97757",
        subtitle=subtitle_text,
        subtitle_align="center",
        padding=(1, 2),
        box=box.ROUNDED,
    )
    console.print(panel)


def print_status_bar(model: str = "", memory: str = "Active"):
    """Print a system status bar showing key indicators."""
    status_table = Table(
        show_header=False, 
        show_edge=False, 
        box=None, 
        padding=(0, 2),
        expand=True,
    )
    status_table.add_column(ratio=1)
    status_table.add_column(ratio=1)
    status_table.add_column(ratio=1)

    # Build status items
    mem_badge = Text()
    mem_badge.append(" • ", style="#D97757")
    mem_badge.append("Memory ", style="#E5E5E5")
    mem_badge.append(memory, style="bold #D97757")

    model_badge = Text()
    model_badge.append(" ✧ ", style="#D9A05B")
    model_badge.append("Model ", style="#E5E5E5")
    model_name = model.split("/")[-1] if model else "Loading..."
    model_badge.append(model_name, style="bold #D9A05B")

    mode_badge = Text()
    mode_badge.append(" ◦ ", style="#E5E5E5")
    mode_badge.append("Mode ", style="#E5E5E5")
    mode_badge.append("Text", style="bold #E5E5E5")

    status_table.add_row(mem_badge, Align.center(model_badge), Align.right(mode_badge))
    
    console.print(Panel(
        status_table, 
        border_style="#333333",
        box=box.ROUNDED,
        padding=(0, 1),
    ))


# ═══════════════════════════════════════════════════════════════════════════════
# Setup Wizard
# ═══════════════════════════════════════════════════════════════════════════════

def setup_environment():
    """Run interactive wizard if .env is missing — with premium styling."""
    if not os.path.exists(".env"):
        welcome = Text()
        welcome.append("\n  ✦  ", style="#D9A05B")
        welcome.append("Welcome to Parker AI", style="bold #D97757")
        welcome.append("  ✦\n\n", style="#D9A05B")
        welcome.append("  It looks like this is your first time.\n", style="#E5E5E5")
        welcome.append("  Let's get you set up in 3 quick steps.\n", style="dim #E5E5E5")
        
        console.print(Panel(
            welcome,
            border_style="#D97757",
            box=box.ROUNDED,
            padding=(1, 2),
        ))
        
        # Step 1: Name
        console.print()
        console.print("  [accent]STEP 1/3[/accent]  [parker]Identity[/parker]")
        name = Prompt.ask("  [user]❯ What should I call you?[/user]")
        
        # Step 2: API Key
        console.print()
        console.print("  [accent]STEP 2/3[/accent]  [parker]API Connection[/parker]")
        console.print("  [muted]Get your key at console.groq.com[/muted]")
        api_key = Prompt.ask("  [user]❯ Paste your Groq API Key[/user]", password=True)
        
        # Step 3: Model Selection
        console.print()
        console.print("  [accent]STEP 3/3[/accent]  [parker]Core Model[/parker]")
        
        model_table = Table(
            show_header=True, 
            header_style="bold #E5E5E5", 
            border_style="#333333",
            box=box.SIMPLE,
            padding=(0, 2),
        )
        model_table.add_column("#", style="#D9A05B", width=3)
        model_table.add_column("Model", style="#D97757")
        model_table.add_column("Description", style="dim #E5E5E5")
        model_table.add_row("1", "Llama 3.3 70B", "★ Recommended — Smartest & Fast")
        model_table.add_row("2", "Mixtral 8x7B", "Great alternative")
        model_table.add_row("3", "Gemma2 9B", "Lightweight")
        console.print(model_table)
        
        choice = Prompt.ask("  [user]❯ Choose a number[/user]", choices=["1", "2", "3"], default="1")
        
        model_map = {
            "1": "llama-3.3-70b-versatile",
            "2": "mixtral-8x7b-32768",
            "3": "gemma2-9b-it"
        }
        selected_model = model_map[choice]
        
        env_content = f"GROQ_API_KEY={api_key}\nUSER_NAME={name}\nCHAT_LLM_MODEL={selected_model}\n"
        
        with open(".env", "w") as f:
            f.write(env_content)
        
        console.print()
        console.print(Panel(
            f"  [parker]✓ Setup complete![/parker]\n"
            f"  [muted]Credentials and model[/muted] [accent]({selected_model})[/accent] [muted]saved to .env[/muted]",
            border_style="#D97757",
            box=box.ROUNDED,
            padding=(1, 2),
        ))
        console.print()


# ═══════════════════════════════════════════════════════════════════════════════
# Message Output
# ═══════════════════════════════════════════════════════════════════════════════

def print_parker(message: str):
    """Print Parker's response with premium cyberpunk styling."""
    # Parker's name with glow icon
    header = Text()
    header.append("  ✧ ", style="#D97757")
    header.append("Parker", style="bold #D97757")
    console.print(header)
    
    # Render markdown response
    md = Markdown(message, code_theme="monokai")
    console.print(md, style="#e0e0e0")
    console.print()


def print_system(message: str):
    """Print system-level information in dim cyan."""
    sys_text = Text()
    sys_text.append("  › ", style="#E5E5E5")
    sys_text.append(message, style="dim italic #E5E5E5")
    console.print(sys_text)


def print_error(message: str):
    """Print error in a red-bordered panel."""
    console.print(Panel(
        f"[error]{message}[/error]",
        title="[badge.red] ✕ ERROR [/badge.red]",
        border_style="#FF1744",
        box=box.ROUNDED,
        padding=(1, 2),
    ))


def print_warning(message: str):
    """Print warning in amber styling."""
    warn_text = Text()
    warn_text.append("  ⚠ ", style="#D9A05B")
    warn_text.append(message, style="bold #D9A05B")
    console.print(warn_text)


def print_success(message: str):
    """Print success message in green."""
    success_text = Text()
    success_text.append("  ✓ ", style="#D97757")
    success_text.append(message, style="bold #D97757")
    console.print(success_text)


def print_header(title: str, icon: str = "✦"):
    """Print a styled section header."""
    header = Text()
    header.append(f"  {icon} ", style="#D9A05B")
    header.append(title, style="bold #E5E5E5")
    console.print(header)


# ═══════════════════════════════════════════════════════════════════════════════
# UI Utilities
# ═══════════════════════════════════════════════════════════════════════════════

def get_spinner(message: str) -> Status:
    """Get a themed spinner for async operations."""
    return console.status(f"[#E5E5E5]  ◌ {message}[/#E5E5E5]", spinner="dots", spinner_style="#D97757")


def print_divider(style: str = "thin"):
    """Print a styled divider."""
    if style == "thick":
        console.print(Rule(style="#D97757", characters="═"))
    else:
        console.print(Rule(style="#333333", characters="─"))


def print_commands_table():
    """Print the available commands in a styled table."""
    table = Table(
        show_header=True,
        header_style="bold #E5E5E5",
        border_style="#333333",
        box=box.SIMPLE,
        padding=(0, 2),
        title="[#D9A05B]Available Commands[/#D9A05B]",
        title_style="bold",
    )
    table.add_column("Key", style="#D97757", width=10)
    table.add_column("Action", style="#e0e0e0")
    
    table.add_row("[bold]t[/bold]",       "Switch to text mode")
    table.add_row("[bold]v[/bold]",       "Switch to voice mode")
    table.add_row("[bold]/clear[/bold]",  "Clear the screen")
    table.add_row("[bold]/profile[/bold]","Show your memory profile")
    table.add_row("[bold]exit[/bold]",    "Save memory & quit")
    
    console.print(table)


def print_profile_panel(profile: dict):
    """Display user profile in a premium formatted panel."""
    import json
    
    table = Table(
        show_header=True,
        header_style="bold #E5E5E5",
        border_style="#333333",
        box=box.SIMPLE,
        padding=(0, 2),
    )
    table.add_column("Key", style="#D97757", width=20)
    table.add_column("Value", style="#e0e0e0")
    
    for key, value in profile.items():
        if isinstance(value, (dict, list)):
            value = json.dumps(value, indent=2)
        table.add_row(str(key), str(value))
    
    console.print(Panel(
        table,
        title="[badge.cyan] ✧ Memory Profile [/badge.cyan]",
        border_style="#E5E5E5",
        box=box.ROUNDED,
        padding=(1, 2),
    ))


def get_user_prompt(mode: str = "text") -> str:
    """Get styled user input prompt string."""
    if mode == "text":
        return "\n[bold #E5E5E5]  ❯ You:[/bold #E5E5E5] "
    else:
        return "\n[bold #E5E5E5]  ❯ You 🎤[/bold #E5E5E5] [dim]press Enter to speak, or 't' to switch:[/dim] "


def print_goodbye():
    """Print a styled farewell message."""
    console.print()
    farewell = Text()
    farewell.append("  ✧ ", style="#D97757")
    farewell.append("Parker is going offline. ", style="#E5E5E5")
    farewell.append("See you soon!", style="bold #D97757")
    console.print(Panel(
        farewell,
        border_style="#D97757",
        box=box.ROUNDED,
        padding=(0, 2),
    ))


def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')
