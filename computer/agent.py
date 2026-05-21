"""
computer/agent.py — Computer use intent parser and action executor for Parker AI

Parker signals computer actions using a structured <computer_action> tag in its response.
This module parses that tag, routes to browser, desktop, or web_search, executes,
and returns a result string that gets injected back into the conversation.
"""

import json
import re
import ast
from typing import Optional


# ── Intent detection ───────────────────────────────────────────────────────────

_ACTION_TAG_PATTERN = re.compile(
    r"<computer_action>(.*?)</computer_action>",
    re.DOTALL | re.IGNORECASE,
)


def clean_and_repair_json(json_str: str):
    """
    Clean markdown code fences, trailing commas, single quotes, and Python-style booleans.
    Parses using json.loads first, then falls back to ast.literal_eval.
    """
    cleaned = json_str.strip()
    
    # Remove markdown code fences if present
    fence_pattern = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)
    match = fence_pattern.match(cleaned)
    if match:
        cleaned = match.group(1).strip()
    else:
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        if cleaned.endswith("```"):
            cleaned = re.sub(r"\s*```$", "", cleaned)
            
    cleaned = cleaned.strip()
    if not cleaned:
        return None

    # Try standard JSON parsing
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Tokenizer to pythonize common JSON differences for literal_eval:
    # 1. replace true -> True, false -> False, null -> None (outside of quoted strings)
    try:
        pattern = re.compile(r'("([^"\\]|\\.)*")|(\'([^\'\\]|\\.)*\')|(\b(true|false|null)\b)', re.DOTALL)
        
        def replace(match):
            val = match.group(5)
            if val:
                if val == "true":
                    return "True"
                elif val == "false":
                    return "False"
                elif val == "null":
                    return "None"
            return match.group(0)
            
        pythonized = pattern.sub(replace, cleaned)
        return ast.literal_eval(pythonized)
    except Exception as e:
        print(f"[JSON Repair Warning] Failed to repair and parse JSON string: {e}")
        return None


def parse_computer_intents(response_text: str) -> list[dict]:
    """
    Extract all computer actions from Parker's response text.
    Handles multiple <computer_action> tags and lists/dicts inside them.
    """
    matches = _ACTION_TAG_PATTERN.findall(response_text)
    intents = []
    for raw in matches:
        parsed = clean_and_repair_json(raw)
        if parsed:
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict):
                        intents.append(item)
            elif isinstance(parsed, dict):
                intents.append(parsed)
    return intents


def parse_computer_intent(response_text: str) -> Optional[dict]:
    """
    Extract a single (first) computer action from Parker's response text.
    Kept for backwards compatibility.
    """
    intents = parse_computer_intents(response_text)
    return intents[0] if intents else None


def strip_action_tag(response_text: str) -> str:
    """Remove the <computer_action> tag from Parker's visible response."""
    return _ACTION_TAG_PATTERN.sub("", response_text).strip()


def execute_computer_actions(intents: list[dict]) -> str:
    """
    Execute multiple computer actions sequentially and format their combined results.
    """
    if not intents:
        return "[Computer Use] No actions to execute."
    
    if len(intents) == 1:
        return execute_computer_action(intents[0])
        
    results = []
    for i, intent in enumerate(intents, 1):
        mode = intent.get("mode", "unknown")
        res = execute_computer_action(intent)
        results.append(f"--- Action {i} ({mode}) Result ---\n{res}")
        
    return "\n\n".join(results)


# ── Action executor ────────────────────────────────────────────────────────────

def execute_computer_action(intent: dict) -> str:
    """
    Route and execute a computer action. Returns a result string
    that Parker will use as context for its follow-up response.

    Intent schema:
        mode:     "web_search" | "browser" | "desktop"
        --- web_search ---
        query:    search query string
        deep:     bool — fetch full page content (default: false)
        category: "general" | "news" | "science" | "it" | "social media" (default: "general")
        --- browser ---
        action:   navigate | get_elements | read_page | click | type | press | search
        target:   URL, element text, app name, etc.
        text:     text to type
        key:      key to press
        --- desktop ---
        action:   list_windows | get_tree | click | type | focus | open
        target:   window/app title
        text:     text to type or control name
    """
    mode = intent.get("mode", "browser")

    try:
        if mode == "api":
            return _execute_api(intent)
        elif mode == "web_search":
            return _execute_web_search(intent)
        elif mode == "browser":
            return _execute_browser_action(intent)
        elif mode == "desktop":
            return _execute_desktop_action(intent)
        else:
            return f"Unknown computer mode: {mode}"
    except ImportError as e:
        return (
            f"[Computer Use] Required library not installed: {e}. "
            f"Run: pip install playwright duckduckgo-search && playwright install chromium"
        )
    except Exception as e:
        return f"[Computer Use] Execution failed: {e}"


def _execute_api(intent: dict) -> str:
    from computer.apis import resolve_intent
    api_intent = intent.get("intent", "")
    params     = intent.get("params", {})
    if not api_intent:
        return "[API] No intent specified."
    print(f"[API] Resolving intent: {api_intent} | params: {params}")
    return resolve_intent(api_intent, params)

# ── Web Search ─────────────────────────────────────────────────────────────────

def _execute_web_search(intent: dict) -> str:
    """Route to SearXNG-backed search layer."""
    from computer.search import web_search

    query    = intent.get("query", "").strip()
    deep     = bool(intent.get("deep", False))
    category = intent.get("category", "general")

    if not query:
        return "[Search] No query provided."

    print(f"[Search] Query: '{query}' | deep={deep} | category={category}")
    return web_search(query=query, deep=deep, category=category)


# ── Browser ────────────────────────────────────────────────────────────────────

def _execute_browser_action(intent: dict) -> str:
    from computer.browser import (
        navigate, get_interactive_elements, click_element,
        type_text, press_key, get_page_text, get_current_url
    )

    action = intent.get("action", "")
    target = intent.get("target", "")
    text   = intent.get("text", "")
    key    = intent.get("key", "")

    if action == "navigate":
        result = navigate(target)
        if result["success"]:
            return f"Navigated to {result['url']} — Title: {result['title']}"
        return f"Navigation failed: {result.get('error')}"

    elif action == "get_elements":
        elements = get_interactive_elements()
        if not elements:
            return "No interactive elements found on page."
        summary = json.dumps(elements[:20], indent=2)
        return f"Interactive elements on {get_current_url()}:\n{summary}"

    elif action == "read_page":
        text_content = get_page_text()
        return f"Page content:\n{text_content}"

    elif action == "click":
        result = click_element(text=target or text)
        if result["success"]:
            return f"Clicked '{target or text}'. Now at: {result.get('new_url', 'same page')}"
        return f"Click failed: {result.get('error')}"

    elif action == "type":
        result = type_text(text=text, target_label=target if target else None)
        if result["success"]:
            return f"Typed '{text}' into '{target or 'focused field'}'"
        return f"Type failed: {result.get('error')}"

    elif action == "press":
        result = press_key(key or target)
        if result["success"]:
            return f"Pressed {key or target}"
        return f"Key press failed: {result.get('error')}"

    elif action == "search":
        if target.startswith("http"):
            navigate(target)
        elements = get_interactive_elements()
        search_inputs = [
            e for e in elements
            if e.get("type") in ("search", "text") or "search" in (e.get("name") or "").lower()
        ]
        if search_inputs:
            result = type_text(text=text)
            if result["success"]:
                press_key("Enter")
                return f"Searched for '{text}' on {get_current_url()}"
        return "Could not find search field on page."

    else:
        return f"Unknown browser action: {action}"


# ── Desktop ────────────────────────────────────────────────────────────────────

def _execute_desktop_action(intent: dict) -> str:
    from computer.desktop import (
        list_open_windows, get_app_tree, click_control,
        type_into_control, focus_window, open_app
    )

    action = intent.get("action", "")
    target = intent.get("target", "")
    text   = intent.get("text", "")

    if action == "list_windows":
        windows = list_open_windows()
        if not windows:
            return "No open windows found."
        names = [w.get("title", "?") for w in windows]
        return f"Open windows: {', '.join(names)}"

    elif action == "get_tree":
        controls = get_app_tree(target)
        if not controls:
            return f"No controls found in '{target}'."
        interactive = [
            c for c in controls
            if c.get("type") in (
                "Button", "Edit", "MenuItem", "CheckBox", "RadioButton", "ComboBox", "Hyperlink"
            ) and c.get("enabled")
        ][:20]
        return f"Controls in '{target}':\n{json.dumps(interactive, indent=2)}"

    elif action == "click":
        result = click_control(app_title=target, control_name=text)
        if result["success"]:
            return f"Clicked '{text}' in '{target}'"
        return f"Click failed: {result.get('error')}"

    elif action == "type":
        result = type_into_control(app_title=target, control_name=intent.get("field", ""), text=text)
        if result["success"]:
            return f"Typed '{text}' into '{target}'"
        return f"Type failed: {result.get('error')}"

    elif action == "focus":
        result = focus_window(target)
        if result["success"]:
            return f"Focused window: '{target}'"
        return f"Focus failed: {result.get('error')}"

    elif action == "open":
        result = open_app(target)
        if result["success"]:
            return f"Launched '{target}'"
        return f"Launch failed: {result.get('error')}"

    else:
        return f"Unknown desktop action: {action}"