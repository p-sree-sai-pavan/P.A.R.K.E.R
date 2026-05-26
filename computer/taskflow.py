import os
import sys
import json
import time
import uuid
import subprocess
from typing import Optional, List, Dict
from computer.sandbox import SANDBOX_DIR, ensure_sandbox_exists

TASKFLOWS_DIR = os.path.join(SANDBOX_DIR, "taskflows")

def ensure_taskflows_dir():
    """Ensure the taskflows directory exists inside the sandbox."""
    ensure_sandbox_exists()
    if not os.path.exists(TASKFLOWS_DIR):
        os.makedirs(TASKFLOWS_DIR)

def start_taskflow(task_name: str, commands: List[str], cwd: Optional[str] = None) -> Dict:
    """
    Initialize a new taskflow, write its metadata, and spawn the background runner.
    """
    ensure_taskflows_dir()
    
    # Generate unique flow ID
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    rand_id = uuid.uuid4().hex[:6]
    flow_id = f"tf_{timestamp}_{rand_id}"
    
    metadata_path = os.path.join(TASKFLOWS_DIR, f"{flow_id}.json")
    
    # Prepare metadata JSON
    metadata = {
        "flow_id": flow_id,
        "task_name": task_name,
        "status": "running",
        "cwd": cwd or "",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "commands": commands,
        "current_step_index": 0,
        "steps": [{"command": cmd, "status": "pending", "duration": 0.0} for cmd in commands]
    }
    
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
        
    # Spawn the background runner process asynchronously
    runner_script = os.path.abspath(os.path.join(os.path.dirname(__file__), "taskflow_runner.py"))
    
    # Run the python runner script in the background
    # Using sys.executable to run inside the same virtual environment
    pypath = sys.executable
    
    try:
        if os.name == "nt":
            # On Windows, we spawn using native flags to detach the process group and breakaway from job objects.
            # DETACHED_PROCESS = 0x00000008, CREATE_BREAKAWAY_FROM_JOB = 0x01000000
            creationflags = 0x00000008 | 0x01000000
            subprocess.Popen(
                [pypath, runner_script, flow_id],
                creationflags=creationflags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True
            )
        else:
            # On Unix-like systems, setsid (start_new_session) detaches the child from the terminal session.
            subprocess.Popen(
                [pypath, runner_script, flow_id],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                start_new_session=True
            )
        return {
            "success": True,
            "flow_id": flow_id,
            "task_name": task_name,
            "status": "running",
            "message": f"Successfully started taskflow '{flow_id}' in background."
        }
    except Exception as e:
        # Update metadata to show failure to spawn
        metadata["status"] = "failed"
        metadata["error"] = f"Failed to spawn runner: {e}"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
        return {
            "success": False,
            "flow_id": flow_id,
            "error": str(e)
        }

def list_taskflows() -> List[Dict]:
    """List all taskflows saved in the taskflows directory."""
    ensure_taskflows_dir()
    flows = []
    
    for filename in os.listdir(TASKFLOWS_DIR):
        if filename.endswith(".json"):
            path = os.path.join(TASKFLOWS_DIR, filename)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    flows.append(data)
            except Exception:
                pass
                
    # Sort by creation date or timestamp descending (newest first)
    flows.sort(key=lambda x: x.get("flow_id", ""), reverse=True)
    return flows

def get_taskflow(flow_id: str) -> Optional[Dict]:
    """Retrieve details of a specific taskflow."""
    ensure_taskflows_dir()
    path = os.path.join(TASKFLOWS_DIR, f"{flow_id}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def read_taskflow_log(flow_id: str) -> str:
    """Read the log file associated with a taskflow."""
    ensure_taskflows_dir()
    path = os.path.join(TASKFLOWS_DIR, f"{flow_id}.log")
    if not os.path.exists(path):
        return f"No log file found for taskflow '{flow_id}'."
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        return f"Error reading log file: {e}"
