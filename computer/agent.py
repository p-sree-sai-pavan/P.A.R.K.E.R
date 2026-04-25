"""
computer/agent.py — Computer use intent parser and action executor for Parker AI

Parker signals computer actions using a structured <computer_action> tag in its response.
This module parses that tag, routes to browser or desktop, executes, and returns a result
string that gets injected back into the conversation.
"""

import json
import re
from typing import Optional


# ── Intent detection ───────────────────────────────────────────────────────────

_ACTION_TAG_PATTERN = re.compile(
    r"<computer_action>(.*?)</computer_action>",
    re.DOTALL | re.IGNORECASE,
)


def parse_computer_intent(response_text: str) -> Optional[dict]:
    """
    Extract a computer action from Parker's response text.
    Returns None if no action is present.

    Expected format in Parker's response:
        <computer_action>{"mode": "browser", "action": "navigate", "target": "https://google.com"}</computer_action>
    """
    match = _ACTION_TAG_PATTERN.search(response_text)
    if not match:
        return None

    try:
        intent = json.loads(match.group(1).strip())
        return intent if isinstance(intent, dict) else None
    except (json.JSONDecodeError, Exception):
        return None


def strip_action_tag(response_text: str) -> str:
    """Remove the <computer_action> tag from Parker's visible response."""
    return _ACTION_TAG_PATTERN.sub("", response_text).strip()


# ── Action executor ────────────────────────────────────────────────────────────

def execute_computer_action(intent: dict) -> str:
    """
    Route and execute a computer action. Returns a result string
    that Parker will use as context for its follow-up response.

    Intent schema:
        mode:   "browser" | "desktop"
        action: depends on mode (see below)
        target: URL, app name, element text, etc.
        text:   text to type (for type actions)
        key:    key to press (for key actions)
    """
    mode = intent.get("mode", "browser")
    action = intent.get("action", "")

    try:
        if mode == "browser":
            return _execute_browser_action(intent)
        elif mode == "desktop":
            return _execute_desktop_action(intent)
        else:
            return f"Unknown computer mode: {mode}"
    except ImportError as e:
        return f"[Computer Use] Required library not installed: {e}. Run: pip install playwright pywinauto && playwright install chromium"
    except Exception as e:
        return f"[Computer Use] Execution failed: {e}"


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
        # Composite: navigate → type → press Enter
        if target.startswith("http"):
            navigate(target)
        elements = get_interactive_elements()
        search_inputs = [e for e in elements if e.get("type") in ("search", "text") or "search" in (e.get("name") or "").lower()]
        if search_inputs:
            result = type_text(text=text)
            if result["success"]:
                press_key("Enter")
                return f"Searched for '{text}' on {get_current_url()}"
        return f"Could not find search field on page."

    else:
        return f"Unknown browser action: {action}"


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
        # Summarise — don't dump all
        interactive = [c for c in controls if c.get("type") in (
            "Button", "Edit", "MenuItem", "CheckBox", "RadioButton", "ComboBox", "Hyperlink"
        ) and c.get("enabled")][:20]
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