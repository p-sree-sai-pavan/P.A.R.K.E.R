import os
import sys
import json
import time
import subprocess
import requests
from pathlib import Path
from dotenv import load_dotenv

# Resolve paths
CURRENT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = CURRENT_DIR.parent
SANDBOX_DIR = PROJECT_ROOT / "sandbox"
TASKFLOWS_DIR = SANDBOX_DIR / "taskflows"

def load_environment():
    """Load environment variables from project .env file."""
    env_path = PROJECT_ROOT / ".env"
    load_dotenv(env_path)

def send_telegram_notification(message: str):
    """Send a notification to the allowed user via Telegram."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    allowed_user = os.getenv("TELEGRAM_ALLOWED_USER")
    
    if not token or not allowed_user:
        print("[TaskFlow Runner] Error: Telegram bot token or allowed user is not set.", file=sys.stderr)
        return
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": allowed_user,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code != 200:
            print(f"[TaskFlow Runner] Telegram API returned code {resp.status_code}: {resp.text}", file=sys.stderr)
    except Exception as e:
        print(f"[TaskFlow Runner] Failed to send Telegram message: {e}", file=sys.stderr)

def main():
    if len(sys.argv) < 2:
        print("Usage: python taskflow_runner.py <flow_id>", file=sys.stderr)
        sys.exit(1)
        
    flow_id = sys.argv[1]
    load_environment()
    
    metadata_path = TASKFLOWS_DIR / f"{flow_id}.json"
    log_path = TASKFLOWS_DIR / f"{flow_id}.log"
    
    if not metadata_path.exists():
        print(f"Error: Metadata file {metadata_path} not found.", file=sys.stderr)
        sys.exit(1)
        
    # Load metadata
    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
    except Exception as e:
        print(f"Error loading metadata: {e}", file=sys.stderr)
        sys.exit(1)
        
    task_name = metadata.get("task_name", "Unnamed Task")
    commands = metadata.get("commands", [])
    cwd_rel = metadata.get("cwd", "")
    
    # Resolve CWD inside sandbox
    cwd = SANDBOX_DIR
    if cwd_rel:
        cwd = (SANDBOX_DIR / cwd_rel).resolve()
        # Security safety check
        if not str(cwd).startswith(str(SANDBOX_DIR)):
            cwd = SANDBOX_DIR
            
    # Make sure CWD exists
    os.makedirs(cwd, exist_ok=True)
    
    # Notify start
    start_message = f"<b>[TaskFlow Started]</b>\n<b>Task:</b> {task_name}\n<b>ID:</b> <code>{flow_id}</code>\n<b>Steps:</b> {len(commands)}"
    send_telegram_notification(start_message)
    
    # Prepare logs
    with open(log_path, "w", encoding="utf-8") as log_file:
        log_file.write(f"TaskFlow Log: {task_name}\n")
        log_file.write(f"Flow ID: {flow_id}\n")
        log_file.write(f"Started at: {metadata['created_at']}\n")
        log_file.write(f"Execution CWD: {cwd}\n")
        log_file.write("==================================================\n\n")
        
    total_steps = len(commands)
    failed = False
    error_summary = ""
    failed_cmd = ""
    
    for idx, cmd in enumerate(commands):
        # Update metadata state to running for this step
        metadata["current_step_index"] = idx
        metadata["steps"][idx]["status"] = "running"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
            
        step_start_time = time.time()
        
        with open(log_path, "a", encoding="utf-8") as log_file:
            log_file.write(f"\n>>> [Step {idx+1}/{total_steps}] Executing: {cmd}\n")
            log_file.write("--------------------------------------------------\n")
            log_file.flush()
            
            # Setup command for shell execution
            shell_cmd = ["powershell", "-Command", cmd] if os.name == "nt" else ["/bin/sh", "-c", cmd]
            
            try:
                process = subprocess.Popen(
                    shell_cmd,
                    cwd=cwd,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True
                )
                process.wait()
                exit_code = process.returncode
            except Exception as e:
                exit_code = -1
                log_file.write(f"\n[Execution Exception] {e}\n")
                
            duration = round(time.time() - step_start_time, 2)
            metadata["steps"][idx]["duration"] = duration
            
            if exit_code == 0:
                metadata["steps"][idx]["status"] = "succeeded"
                log_file.write(f"\n<<< [Step {idx+1}/{total_steps}] Succeeded in {duration}s\n")
            else:
                metadata["steps"][idx]["status"] = "failed"
                log_file.write(f"\n<<< [Step {idx+1}/{total_steps}] Failed with exit code {exit_code} in {duration}s\n")
                failed = True
                failed_cmd = cmd
                error_summary = f"Step {idx+1} failed with exit code {exit_code}."
                break
                
    # Update final flow metadata
    metadata["ended_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    if failed:
        metadata["status"] = "failed"
        metadata["error"] = error_summary
        
        # Send failure Telegram alert
        log_preview = f"Step failed: <code>{failed_cmd}</code>\n{error_summary}"
        fail_message = (
            f"❌ <b>[TaskFlow Failed]</b>\n"
            f"<b>Task:</b> {task_name}\n"
            f"<b>ID:</b> <code>{flow_id}</code>\n"
            f"<b>Details:</b> {log_preview}\n"
            f"Please check logs in sandbox: <code>taskflows/{flow_id}.log</code>"
        )
        send_telegram_notification(fail_message)
    else:
        metadata["status"] = "succeeded"
        
        # Send success Telegram alert
        success_message = (
            f"✅ <b>[TaskFlow Completed]</b>\n"
            f"<b>Task:</b> {task_name}\n"
            f"<b>ID:</b> <code>{flow_id}</code>\n"
            f"All {total_steps} steps completed successfully."
        )
        send_telegram_notification(success_message)
        
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

if __name__ == "__main__":
    main()
