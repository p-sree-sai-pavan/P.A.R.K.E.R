import os
import subprocess
import shutil
from typing import Optional

SANDBOX_DIR = os.path.abspath("sandbox")

def ensure_sandbox_exists():
    """Ensure the sandbox directory exists."""
    if not os.path.exists(SANDBOX_DIR):
        os.makedirs(SANDBOX_DIR)
        # Create a README in the sandbox folder
        readme_path = os.path.join(SANDBOX_DIR, "README.md")
        with open(readme_path, "w") as f:
            f.write("# Parker Sandbox\n\nThis directory is a safe execution workspace for Parker. All file modifications and shell commands run by Parker must stay inside this directory.\n")

def _resolve_path(rel_path: str) -> str:
    """
    Safely resolve a relative path to an absolute path inside the sandbox directory.
    Raises PermissionError if a path traversal attack is attempted.
    """
    ensure_sandbox_exists()
    
    # Clean and resolve path
    normalized_rel = os.path.normpath(rel_path)
    if normalized_rel.startswith(os.pardir) or os.path.isabs(normalized_rel):
        # Even if it looks absolute, check if it's already inside sandbox
        abs_target = os.path.abspath(normalized_rel)
        if not abs_target.startswith(SANDBOX_DIR):
            raise PermissionError(f"Access Denied: Path '{rel_path}' is outside the sandbox.")
        return abs_target
        
    abs_target = os.path.abspath(os.path.join(SANDBOX_DIR, normalized_rel))
    if not abs_target.startswith(SANDBOX_DIR):
        raise PermissionError(f"Access Denied: Path '{rel_path}' resolves outside the sandbox.")
    return abs_target

def write_sandbox_file(file_path: str, content: str) -> str:
    """Write text content to a file inside the sandbox."""
    try:
        abs_path = _resolve_path(file_path)
        # Ensure parent folder exists
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote {len(content)} characters to sandbox/{file_path}"
    except Exception as e:
        return f"Error writing file: {e}"

def read_sandbox_file(file_path: str) -> str:
    """Read and return text content from a file inside the sandbox or allowed gateway skills."""
    try:
        # Check if the path points to gateway skills
        abs_path = os.path.abspath(file_path)
        gateway_skills = os.path.abspath(os.path.join(SANDBOX_DIR, "..", "gateway", "skills"))
        gateway_agents_skills = os.path.abspath(os.path.join(SANDBOX_DIR, "..", "gateway", ".agents", "skills"))
        
        is_skill_file = False
        if abs_path.startswith(gateway_skills) or abs_path.startswith(gateway_agents_skills):
            is_skill_file = True
        else:
            # Handle relative path references (like gateway/skills/weather/SKILL.md)
            norm_rel = os.path.normpath(file_path)
            candidate_abs = os.path.abspath(os.path.join(SANDBOX_DIR, "..", norm_rel))
            if candidate_abs.startswith(gateway_skills) or candidate_abs.startswith(gateway_agents_skills):
                abs_path = candidate_abs
                is_skill_file = True

        if not is_skill_file:
            abs_path = _resolve_path(file_path)

        if not os.path.exists(abs_path):
            return f"Error: {file_path} does not exist."
        if os.path.isdir(abs_path):
            return f"Error: {file_path} is a directory."
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {e}"

def list_sandbox_files(dir_path: str = ".") -> str:
    """List directory contents inside the sandbox."""
    try:
        abs_path = _resolve_path(dir_path)
        if not os.path.exists(abs_path):
            return f"Error: sandbox/{dir_path} does not exist."
        if not os.path.isdir(abs_path):
            return f"Error: sandbox/{dir_path} is a file, not a directory."
            
        items = os.listdir(abs_path)
        if not items:
            return f"sandbox/{dir_path} is empty."
            
        result = []
        for item in items:
            full_item = os.path.join(abs_path, item)
            is_dir = os.path.isdir(full_item)
            size = os.path.getsize(full_item) if not is_dir else 0
            type_label = "[DIR]" if is_dir else "[FILE]"
            size_label = f" ({size} bytes)" if not is_dir else ""
            result.append(f"{type_label} {item}{size_label}")
            
        return f"Contents of sandbox/{dir_path}:\n" + "\n".join(result)
    except Exception as e:
        return f"Error listing directory: {e}"

def run_sandbox_command(command: str) -> str:
    """
    Run a shell command inside the sandbox directory.
    Uses powershell on Windows, bash on Linux/macOS.
    """
    ensure_sandbox_exists()
    
    # Basic safety filter: block known destructive or system-breaking commands
    blocked_keywords = ["rmdir /s", "rm -rf /", "format", "shutdown", "del /s", "mkfs", "dd"]
    for kw in blocked_keywords:
        if kw in command.lower():
            return f"Error: Command blocked due to safety policy: containing '{kw}'"
            
    try:
        # Enforce execution context inside sandbox
        print(f"[Sandbox] Executing: {command}")
        
        # On Windows, run in powershell
        shell_cmd = ["powershell", "-Command", command] if os.name == "nt" else ["/bin/sh", "-c", command]
        
        res = subprocess.run(
            shell_cmd,
            cwd=SANDBOX_DIR,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        output = ""
        if res.stdout:
            output += f"--- STDOUT ---\n{res.stdout}\n"
        if res.stderr:
            output += f"--- STDERR ---\n{res.stderr}\n"
            
        if not output:
            output = "Command finished with no output."
            
        return f"Command execution completed (exit code: {res.returncode}).\n{output}"
    except subprocess.TimeoutExpired:
        return "Error: Command execution timed out (limit: 10s)."
    except Exception as e:
        return f"Error running command: {e}"
