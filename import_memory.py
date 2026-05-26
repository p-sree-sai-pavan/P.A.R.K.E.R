"""
import_memory.py — Utility to import user profile, facts, tasks, and projects from external exports.
"""
import os
import sys
import json
import argparse
import uuid
import time
import re
from datetime import datetime

from rich.table import Table
from rich.panel import Panel
from rich import box

# Ensure root folder is in path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

try:
    from database import create_store, close_connections
    from config import DEFAULT_USER_ID
    from memory.profile import load_profile, PROFILE_KEY, NAMESPACE as PROFILE_NS
    from memory.facts import NAMESPACE as FACTS_NS
    from memory.projects import NAMESPACE as PROJECTS_NS
    from memory.tasks import NAMESPACE as TASKS_NS
    from interface import console
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Please make sure you are running this script from the P.A.R.K.E.R project root.")
    sys.exit(1)

def import_profile(store, user_id: str, profile_data: dict) -> int:
    ns = PROFILE_NS(user_id)
    existing = load_profile(store, user_id)
    updated = existing.copy()
    
    count = 0
    for k, v in profile_data.items():
        if v not in (None, "", [], {}):
            updated[k] = v
            count += 1
            
    if count > 0:
        store.put(ns, PROFILE_KEY, updated)
    return count

def import_facts(store, user_id: str, facts_list: list) -> int:
    ns = FACTS_NS(user_id)
    now = time.time()
    count = 0
    
    for item in facts_list:
        content = ""
        importance = "normal"
        category = ""
        
        if isinstance(item, str):
            content = item.strip()
        elif isinstance(item, dict):
            content = item.get("content", "").strip()
            importance = item.get("importance", "normal").strip()
            category = item.get("category", "").strip()
            
        if not content:
            continue
            
        if not category:
            # Generate a clean short key
            words = [w for w in content.lower().split() if len(w) > 3]
            category = "_".join(words[:3]) or f"fact_{str(uuid.uuid4())[:8]}"
            
        # Limit key size & sanitize
        category = "".join(c for c in category if c.isalnum() or c in ("_", "-"))[:60]
        
        store.put(ns, category, {
            "content": content,
            "importance": importance,
            "updated_at": now,
            "created_at": now,
            "text": content
        })
        count += 1
        
    return count

def import_projects(store, user_id: str, projects_list: list) -> int:
    ns = PROJECTS_NS(user_id)
    now = time.time()
    count = 0
    
    for proj in projects_list:
        if not isinstance(proj, dict):
            continue
        name = proj.get("name", "").strip()
        if not name:
            continue
            
        key = name.lower().replace(" ", "_")
        key = "".join(c for c in key if c.isalnum() or c == "_")[:60]
        
        status = proj.get("status", "active")
        stack = proj.get("stack", [])
        summary = proj.get("summary", "")
        
        # Build indexable search text
        search_text = f"Project: {name}. Status: {status}. Stack: {', '.join(stack)}. Summary: {summary}"
        
        store.put(ns, key, {
            "name": name,
            "status": status,
            "stack": stack,
            "summary": summary,
            "open_threads": proj.get("open_threads", []),
            "decisions_log": proj.get("decisions_log", []),
            "last_touched": proj.get("last_touched") or datetime.now().strftime("%Y-%m-%d"),
            "text": search_text
        })
        count += 1
        
    return count

def import_tasks(store, user_id: str, tasks_list: list) -> int:
    ns = TASKS_NS(user_id)
    count = 0
    
    for task in tasks_list:
        content = ""
        priority = "normal"
        due = None
        condition = "none"
        status = "active"
        
        if isinstance(task, str):
            content = task.strip()
        elif isinstance(task, dict):
            content = task.get("content", "").strip()
            priority = task.get("priority", "normal").strip()
            due = task.get("due")
            condition = task.get("condition", "none")
            status = task.get("status", "active")
            
        if not content:
            continue
            
        key = f"task_{str(uuid.uuid4())[:8]}"
        
        store.put(ns, key, {
            "content": content,
            "priority": priority,
            "due": due,
            "condition": condition,
            "status": status,
            "text": content
        })
        count += 1
        
    return count

def parse_conversations_memory(memory_text: str) -> list:
    facts = []
    lines = memory_text.split("\n")
    current_section = ""
    current_subsection = ""
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
            
        if line.startswith("**") and line.endswith("**") and len(line) > 4:
            current_section = line.strip("*")
            current_subsection = ""
            i += 1
            continue
        elif line.startswith("*") and line.endswith("*") and len(line) > 2:
            current_subsection = line.strip("*")
            i += 1
            continue
            
        if line.startswith("* ") or line.startswith("- "):
            bullet_content = line[2:].strip()
            prefix = ""
            if current_section:
                prefix += f"{current_section}"
            if current_subsection:
                prefix += f" ({current_subsection})"
            
            fact = f"{prefix}: {bullet_content}" if prefix else bullet_content
            facts.append(fact)
            i += 1
            continue
            
        paragraph_lines = [line]
        i += 1
        while i < len(lines):
            next_line = lines[i].strip()
            if not next_line:
                break
            if next_line.startswith("**") and next_line.endswith("**") and len(next_line) > 4:
                break
            if next_line.startswith("*") and next_line.endswith("*") and len(next_line) > 2:
                break
            if next_line.startswith("* ") or next_line.startswith("- "):
                break
            paragraph_lines.append(next_line)
            i += 1
            
        paragraph_content = " ".join(paragraph_lines).strip()
        if paragraph_content:
            prefix = ""
            if current_section:
                prefix += f"{current_section}"
            if current_subsection:
                prefix += f" ({current_subsection})"
                
            fact = f"{prefix}: {paragraph_content}" if prefix else paragraph_content
            facts.append(fact)
            
    return facts


def extract_profile_from_memory(memory_text: str) -> dict:
    profile = {}
    
    if "IIT Guwahati" in memory_text:
        profile["institution"] = "IIT Guwahati"
    if "ECE student" in memory_text or "ECE" in memory_text:
        profile["department"] = "ECE"
        
    roll_match = re.search(r"roll number\s+([0-9a-zA-Z]+)", memory_text, re.IGNORECASE)
    if roll_match:
        profile["roll_number"] = roll_match.group(1)
        
    batch_match = re.search(r"batch of\s+([0-9]+)", memory_text, re.IGNORECASE)
    if batch_match:
        profile["batch"] = batch_match.group(1)
        
    cf_match = re.search(r"Codeforces\s+\(handle:\s*([^\s,\)]+)", memory_text, re.IGNORECASE)
    if cf_match:
        profile["codeforces"] = cf_match.group(1)
        
    github_match = re.search(r"GitHub:\s*([^\s,\)]+)", memory_text, re.IGNORECASE)
    if github_match:
        profile["github"] = github_match.group(1)
        
    laptop_match = re.search(r"(HP OMEN laptop[^.\n]*)", memory_text, re.IGNORECASE)
    if laptop_match:
        profile["hardware"] = laptop_match.group(1).strip()
        
    return profile


def import_claude_folder(store, dir_path: str, user_id: str) -> dict:
    stats = {"profile": 0, "facts": 0, "projects": 0, "tasks": 0}
    
    # 1. Import Users from users.json
    users_path = os.path.join(dir_path, "users.json")
    claude_uuid = None
    if os.path.exists(users_path):
        try:
            with open(users_path, "r", encoding="utf-8") as f:
                users_data = json.load(f)
            if isinstance(users_data, list) and len(users_data) > 0:
                user = users_data[0]
                claude_uuid = user.get("uuid")
                profile_update = {
                    "full_name": user.get("full_name"),
                    "email": user.get("email_address"),
                    "claude_account_uuid": claude_uuid
                }
                stats["profile"] += import_profile(store, user_id, profile_update)
        except Exception as e:
            console.print(f"[warning]Failed to process users.json: {e}[/]")
            
    # 2. Import Memories from memories.json
    memories_path = os.path.join(dir_path, "memories.json")
    project_memories = {}
    if os.path.exists(memories_path):
        try:
            with open(memories_path, "r", encoding="utf-8") as f:
                memories_data = json.load(f)
            if isinstance(memories_data, list) and len(memories_data) > 0:
                mem_item = memories_data[0]
                
                # Import distilled facts from conversations_memory
                conv_mem = mem_item.get("conversations_memory", "")
                if conv_mem:
                    parsed_facts = parse_conversations_memory(conv_mem)
                    stats["facts"] += import_facts(store, user_id, parsed_facts)
                    
                    # Extract profile attributes from facts
                    profile_from_facts = extract_profile_from_memory(conv_mem)
                    if profile_from_facts:
                        stats["profile"] += import_profile(store, user_id, profile_from_facts)
                        
                # Extract project summaries map
                project_memories = mem_item.get("project_memories", {})
        except Exception as e:
            console.print(f"[warning]Failed to process memories.json: {e}[/]")
            
    # 3. Import Projects from projects/ directory
    projects_dir = os.path.join(dir_path, "projects")
    if os.path.exists(projects_dir) and os.path.isdir(projects_dir):
        try:
            project_files = [f for f in os.listdir(projects_dir) if f.endswith(".json")]
            projects_ns = PROJECTS_NS(user_id)
            now = time.time()
            
            # Common tech stack keywords for parsing
            stack_keywords = ["Python", "FastAPI", "React", "Node.js", "Express", 
                              "PostgreSQL", "Firestore", "Firebase", "C++", "Docker", 
                              "Redis", "Nginx", "PgBouncer", "k6", "Tailwind", 
                              "JavaScript", "HTML", "CSS", "TypeScript", "Next.js", "Vite"]
                              
            for p_file in project_files:
                p_path = os.path.join(projects_dir, p_file)
                with open(p_path, "r", encoding="utf-8") as f:
                    proj = json.load(f)
                
                name = proj.get("name", "").strip()
                if not name:
                    continue
                    
                p_uuid = proj.get("uuid", "")
                desc = proj.get("description", "").strip()
                
                # Get summary from memories.json if available
                summary = project_memories.get(p_uuid, desc)
                
                # Parse created/updated timestamps
                created_ts = now
                updated_ts = now
                try:
                    if proj.get("created_at"):
                        created_ts = datetime.fromisoformat(proj["created_at"].replace("Z", "+00:00")).timestamp()
                    if proj.get("updated_at"):
                        updated_ts = datetime.fromisoformat(proj["updated_at"].replace("Z", "+00:00")).timestamp()
                except Exception:
                    pass
                    
                # Auto-detect tech stack from summary and description
                stack = []
                for kw in stack_keywords:
                    pattern = r'\b' + re.escape(kw) + r'\b'
                    if re.search(pattern, summary, re.IGNORECASE) or re.search(pattern, desc, re.IGNORECASE):
                        stack.append(kw)
                        
                # Create key name using the normalized approach
                key = name.lower().strip()
                key = re.sub(r"[^a-z0-9]+", "_", key)
                key = key.strip("_")
                if not key:
                    key = f"proj_{str(uuid.uuid4())[:8]}"
                    
                # Build searchable index text
                search_text = f"Project: {name}. Description: {desc}. Summary: {summary}. Stack: {', '.join(stack)}."
                
                docs = proj.get("docs", [])
                if docs:
                    search_text += " Documents:\n"
                    for doc in docs:
                        filename = doc.get("filename", "")
                        content = doc.get("content", "")
                        search_text += f"\n--- Document: {filename} ---\n{content}\n"
                        
                # Insert into DB projects namespace
                store.put(projects_ns, key, {
                    "name": name,
                    "status": "active",
                    "summary": summary,
                    "stack": stack,
                    "open_threads": [],
                    "decisions_log": ["Imported from Claude memory"],
                    "linked_chats": [],
                    "last_touched": datetime.fromtimestamp(updated_ts).strftime("%Y-%m-%d"),
                    "created_at": created_ts,
                    "updated_at": updated_ts,
                    "text": search_text[:2000],  # Truncate to avoid exceeding embedding context length
                    "docs": docs
                })
                stats["projects"] += 1
                
        except Exception as e:
            console.print(f"[warning]Failed to process projects directory: {e}[/]")
            
    return stats


def run_import(file_path: str, user_id: str = DEFAULT_USER_ID) -> dict:
    """
    Core entry point to parse a file or directory and import its contents.
    Returns a dict with summary stats.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
        
    stats = {"profile": 0, "facts": 0, "projects": 0, "tasks": 0}
    store = None
    
    try:
        # Connect to DB
        store = create_store()
        
        if os.path.isdir(file_path):
            stats = import_claude_folder(store, file_path, user_id)
            return stats
            
        # Read file
        ext = os.path.splitext(file_path)[1].lower()
        
        if ext == ".txt":
            # Plain text file — read each line as a fact
            with open(file_path, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
            stats["facts"] = import_facts(store, user_id, lines)
            
        elif ext == ".json":
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            # Detect schema
            # Case 1: ChatGPT memories/profile export
            if isinstance(data, dict) and "memories" in data and isinstance(data["memories"], list):
                # Extract memories list
                m_list = []
                for item in data["memories"]:
                    if isinstance(item, dict) and "content" in item:
                        m_list.append(item["content"])
                    elif isinstance(item, str):
                        m_list.append(item)
                stats["facts"] = import_facts(store, user_id, m_list)
                
            # Case 2: Structured JSON export with namespaces
            elif isinstance(data, dict) and any(k in data for k in ("profile", "facts", "projects", "tasks")):
                if "profile" in data and isinstance(data["profile"], dict):
                    stats["profile"] = import_profile(store, user_id, data["profile"])
                if "facts" in data and isinstance(data["facts"], list):
                    stats["facts"] = import_facts(store, user_id, data["facts"])
                if "projects" in data and isinstance(data["projects"], list):
                    stats["projects"] = import_projects(store, user_id, data["projects"])
                if "tasks" in data and isinstance(data["tasks"], list):
                    stats["tasks"] = import_tasks(store, user_id, data["tasks"])
                    
            # Case 3: Flat array of strings
            elif isinstance(data, list):
                stats["facts"] = import_facts(store, user_id, data)
                
            # Case 4: Random dictionary — treat as profile key-values
            elif isinstance(data, dict):
                stats["profile"] = import_profile(store, user_id, data)
        else:
            raise ValueError("Unsupported file format. Please use a .json or .txt file.")
            
    finally:
        if store:
            close_connections()
            
    return stats

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import user profile, facts, tasks, and projects into Parker.")
    parser.add_argument("file", help="Path to JSON or TXT file to import.")
    parser.add_argument("--user-id", default=DEFAULT_USER_ID, help=f"Target user ID (default: {DEFAULT_USER_ID}).")
    args = parser.parse_args()
    
    console.print(Panel(
        f"[bold pk]Parker Memory Importer[/]\nImporting from: [tx.bold]{args.file}[/]\nUser ID: [tx.bold]{args.user_id}[/]",
        border_style="pk",
        box=box.ROUNDED
    ))
    
    try:
        stats = run_import(args.file, args.user_id)
        
        t = Table(show_header=True, header_style="ac.bold", box=box.ROUNDED, border_style="border")
        t.add_column("Category", style="pk")
        t.add_column("Items Imported", style="tx.bold", justify="right")
        
        for k, v in stats.items():
            t.add_row(k, str(v))
            
        console.print(t)
        console.print("\n[ok]✓ Import completed successfully.[/]\n")
    except Exception as e:
        console.print(f"\n[err]Import failed: {e}[/]\n")
        sys.exit(1)
