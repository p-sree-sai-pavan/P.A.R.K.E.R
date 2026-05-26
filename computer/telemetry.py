import os
import time
import subprocess
import ctypes
from typing import Optional

def get_active_window_title() -> str:
    """
    Get the title of the currently focused window on Windows using native ctypes.
    """
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return "Unknown (Idle)"
        buf = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value
    except Exception:
        return "Unknown"

def get_git_status(path: str = ".") -> str:
    """
    Get a short summary of modified or untracked files in the git repo.
    """
    try:
        res = subprocess.run(
            ["git", "status", "-s"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=2
        )
        if res.returncode == 0:
            status = res.stdout.strip()
            return status if status else "Clean (No modifications)"
        return "Not a git repository or git not installed"
    except Exception as e:
        return f"Error reading git status: {e}"

def get_recently_modified_files(path: str = ".", hours: float = 2.0) -> list[str]:
    """
    Scan the workspace for files modified within the last N hours.
    Ignores common build, dependency, and hidden directories.
    """
    ignored_dirs = {
        "venv", "env", ".git", ".claude", "__pycache__", ".vscode", "searxng",
        "node_modules", "dist", "build", "brain", ".gemini"
    }
    recent_files = []
    now = time.time()
    max_age = hours * 3600

    try:
        for root, dirs, files in os.walk(path):
            # Prune ignored directories in-place
            dirs[:] = [d for d in dirs if d not in ignored_dirs and not d.startswith(".")]
            
            for file in files:
                if file.startswith("."):
                    continue
                file_path = os.path.join(root, file)
                try:
                    mtime = os.path.getmtime(file_path)
                    if now - mtime < max_age:
                        rel_path = os.path.relpath(file_path, path)
                        recent_files.append(rel_path)
                except (OSError, FileNotFoundError):
                    continue
                
                # Cap the list to avoid overwhelming the prompt
                if len(recent_files) >= 10:
                    break
            if len(recent_files) >= 10:
                break
    except Exception:
        pass
    
    return recent_files

def get_system_telemetry(workspace_path: str = ".") -> dict:
    """
    Aggregate all environment telemetry.
    """
    return {
        "active_window": get_active_window_title(),
        "git_status": get_git_status(workspace_path),
        "recent_files": get_recently_modified_files(workspace_path, hours=2.0)
    }

def format_telemetry_for_prompt(telemetry: dict) -> str:
    """
    Format telemetry dict into a clean string for Parker's prompt.
    """
    lines = []
    lines.append(f"Active Window: {telemetry['active_window']}")
    lines.append(f"Git Repository Status:\n{telemetry['git_status']}")
    
    recent = telemetry["recent_files"]
    if recent:
        lines.append("Recently Modified Files (last 2 hours):")
        for f in recent:
            lines.append(f"  - {f}")
    else:
        lines.append("Recently Modified Files: None")
        
    return "\n".join(lines)
