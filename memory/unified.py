import json
import time
import re
from datetime import datetime
from langchain_core.messages import SystemMessage, HumanMessage

from models import rollup_llm as unified_llm  # Uses Qwen 32B by default on Groq, falls back to local Ollama Qwen 7B
from prompts.memory import UNIFIED_MEMORY_PROMPT
from memory.utils import (
    format_messages, parse_json_object, get_ns_lock, start_background_job, full_scan
)
from memory.facts import NAMESPACE as FACTS_NS
from memory.profile import NAMESPACE as PROFILE_NS, PROFILE_KEY
from memory.projects import NAMESPACE as PROJECTS_NS
from memory.tasks import NAMESPACE as TASKS_NS

# Import formatting helpers to construct the existing states
from memory.facts import _format_existing_for_prompt as format_facts
from memory.profile import format_for_prompt as format_profile
from memory.projects import _format_existing_for_prompt as format_projects
from memory.tasks import _format_existing_for_prompt as format_tasks


def save_memory_updates(store, user_id: str, messages: list):
    """
    Triggers a single, unified memory extraction background thread.
    """
    start_background_job(
        _extract_and_save_unified,
        store,
        user_id,
        messages,
        name="unified-memory-save",
    )


def sanitize_key(name: str) -> str:
    key = name.lower().strip()
    key = re.sub(r"[^a-z0-9]+", "_", key)
    key = key.strip("_")
    return key


def _extract_and_save_unified(store, user_id: str, messages: list):
    # Lock all four namespaces to ensure atomic read-modify-write across background updates
    with get_ns_lock(FACTS_NS(user_id)), get_ns_lock(PROFILE_NS(user_id)), get_ns_lock(PROJECTS_NS(user_id)), get_ns_lock(TASKS_NS(user_id)):
        try:
            # 1. Load existing state
            existing_facts = full_scan(store, FACTS_NS(user_id))
            existing_profile = full_scan(store, PROFILE_NS(user_id))
            existing_profile_dict = existing_profile[0].value if existing_profile else {}
            existing_projects = full_scan(store, PROJECTS_NS(user_id))
            existing_tasks = full_scan(store, TASKS_NS(user_id))
            
            # 2. Format existing states for prompt
            facts_text = format_facts(existing_facts)
            profile_text = format_profile(existing_profile_dict)
            projects_text = format_projects(existing_projects)
            tasks_text = format_tasks(existing_tasks)
            
            conversation = format_messages(messages)
            current_time_str = datetime.now().isoformat()
            
            response = unified_llm.invoke([
                SystemMessage(content=UNIFIED_MEMORY_PROMPT.format(
                    current_time=current_time_str,
                    existing_profile=profile_text,
                    existing_facts=facts_text,
                    existing_tasks=tasks_text,
                    existing_projects=projects_text,
                    conversation=conversation
                )),
                HumanMessage(content="Extract memory updates.")
            ])
            
            from memory.utils import get_message_content
            response_text = get_message_content(response)
            extracted = parse_json_object(response_text)
            if not extracted:
                return
                
            now = time.time()

            # 3. Process Profile Updates
            profile_updates = extracted.get("profile_updates", {})
            if profile_updates and isinstance(profile_updates, dict):
                updated_profile = existing_profile_dict.copy()
                for k, v in profile_updates.items():
                    if v not in (None, "", [], {}):
                        updated_profile[k] = v
                store.put(PROFILE_NS(user_id), PROFILE_KEY, updated_profile)
                print(f"[Memory] Profile updated: {list(profile_updates.keys())}")
                
            # 4. Process Facts
            facts = extracted.get("facts", [])
            if facts and isinstance(facts, list):
                for fact in facts:
                    if not isinstance(fact, dict):
                        continue
                    action = fact.get("action", "add").strip()
                    category = fact.get("category", "").strip()
                    content = fact.get("content", "").strip()
                    importance = fact.get("importance", "normal").strip()
                    
                    if not category or not content or action == "skip":
                        continue
                        
                    existing_match = None
                    for item in existing_facts:
                        if item.key == category:
                            existing_match = item
                            break
                            
                    store.put(FACTS_NS(user_id), category, {
                        "content": content,
                        "importance": importance,
                        "updated_at": now,
                        "created_at": existing_match.value.get("created_at", now) if existing_match else now,
                        "text": content,
                    })
                    print(f"[Memory] Fact {action.upper()}: {category}")
                
            # 5. Process Projects
            projects = extracted.get("projects", [])
            if projects and isinstance(projects, list):
                for proj in projects:
                    if not isinstance(proj, dict):
                        continue
                    action = proj.get("action", "add").strip()
                    name = proj.get("name", "").strip()
                    status = proj.get("status", "active").strip()
                    summary = proj.get("summary", "").strip()
                    stack = proj.get("stack", [])
                    open_threads = proj.get("open_threads", [])
                    decisions = proj.get("decisions", [])
                    
                    if not name or action == "skip":
                        continue
                        
                    key = sanitize_key(name)
                    
                    existing_match = None
                    for item in existing_projects:
                        if item.key == key:
                            existing_match = item
                            break
                            
                    created_at = existing_match.value.get("created_at", now) if existing_match else now
                    
                    # Deduplicate decisions and open threads if updating
                    if existing_match and action == "update":
                        prev = existing_match.value
                        prev_decisions = prev.get("decisions", [])
                        prev_threads = prev.get("open_threads", [])
                        
                        decisions = list(dict.fromkeys(prev_decisions + decisions))
                    
                    store.put(PROJECTS_NS(user_id), key, {
                        "name": name,
                        "status": status,
                        "summary": summary,
                        "stack": stack,
                        "open_threads": open_threads,
                        "decisions": decisions,
                        "created_at": created_at,
                        "updated_at": now,
                    })
                    print(f"[Memory] Project {action.upper()}: {name}")
                
            # 6. Process Tasks
            tasks = extracted.get("tasks", [])
            if tasks and isinstance(tasks, list):
                for task in tasks:
                    if not isinstance(task, dict):
                        continue
                    action = task.get("action", "add").strip()
                    key = task.get("key", "").strip()
                    content = task.get("content", "").strip()
                    t_type = task.get("type", "reminder").strip()
                    condition = task.get("condition", "none").strip()
                    priority = task.get("priority", "normal").strip()
                    due = task.get("due")
                    
                    if not key or action == "skip":
                        continue
                        
                    existing_match = None
                    for item in existing_tasks:
                        if item.key == key:
                            existing_match = item
                            break
                            
                    if action == "complete":
                        if existing_match:
                            val = existing_match.value.copy()
                            val["status"] = "completed"
                            val["completed_at"] = now
                            store.put(TASKS_NS(user_id), key, val)
                            print(f"[Memory] Task COMPLETED: {key}")
                        continue
                        
                    created_at = existing_match.value.get("created_at", now) if existing_match else now
                    
                    store.put(TASKS_NS(user_id), key, {
                        "content": content,
                        "type": t_type,
                        "condition": condition,
                        "priority": priority,
                        "due": due,
                        "status": "pending",
                        "created_at": created_at,
                        "updated_at": now,
                    })
                    print(f"[Memory] Task {action.upper()}: {key}")
                
        except Exception as e:
            print(f"[Memory] Unified extraction failed: {e}")
