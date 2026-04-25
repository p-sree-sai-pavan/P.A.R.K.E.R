"""
computer/desktop.py — Windows Accessibility Tree controller for Parker AI

Uses pywinauto's UIA backend to read and control desktop apps.
No screenshots. Pure structured control tree — fast and exact.
"""

import time
from typing import Optional


def list_open_windows() -> list[dict]:
    """
    Return all currently open top-level windows.
    Useful for Parker to know what's running.
    """
    try:
        from pywinauto import Desktop
        windows = Desktop(backend="uia").windows()
        result = []
        for w in windows:
            try:
                title = w.window_text().strip()
                if title:
                    result.append({
                        "title": title,
                        "class": w.friendly_class_name(),
                    })
            except Exception:
                continue
        return result
    except Exception as e:
        return [{"error": str(e)}]


def get_app_tree(app_title: str, max_controls: int = 60) -> list[dict]:
    """
    Get all interactive controls from a desktop app window.
    Returns structured list of controls Parker can act on.
    """
    try:
        from pywinauto import Desktop
        app = Desktop(backend="uia").window(title_re=f".*{app_title}.*", found_index=0)
        app.set_focus()
        time.sleep(0.3)

        controls = []
        for ctrl in app.descendants():
            try:
                name = ctrl.window_text().strip()
                ctrl_type = ctrl.friendly_class_name()

                # Only include interactive or informative controls
                if ctrl_type in ("Static", "Pane", "Document") and not name:
                    continue

                rect = ctrl.rectangle()
                controls.append({
                    "name": name or "(unnamed)",
                    "type": ctrl_type,
                    "enabled": ctrl.is_enabled(),
                    "rect": {
                        "left": rect.left,
                        "top": rect.top,
                        "right": rect.right,
                        "bottom": rect.bottom,
                    },
                })
                if len(controls) >= max_controls:
                    break
            except Exception:
                continue

        return controls
    except Exception as e:
        return [{"error": str(e)}]


def click_control(app_title: str, control_name: str, control_type: str = None) -> dict:
    """
    Click a named control in a desktop app.
    Optionally filter by control type for precision.
    """
    try:
        from pywinauto import Desktop
        app = Desktop(backend="uia").window(title_re=f".*{app_title}.*", found_index=0)
        app.set_focus()
        time.sleep(0.2)

        if control_type:
            ctrl = app.child_window(title=control_name, control_type=control_type)
        else:
            ctrl = app.child_window(title=control_name)

        ctrl.click_input()
        time.sleep(0.3)
        return {"success": True, "clicked": control_name}
    except Exception as e:
        return {"success": False, "error": str(e)}


def type_into_control(app_title: str, control_name: str, text: str) -> dict:
    """
    Type text into a named control (e.g. a text field) in a desktop app.
    """
    try:
        from pywinauto import Desktop
        app = Desktop(backend="uia").window(title_re=f".*{app_title}.*", found_index=0)
        app.set_focus()

        ctrl = app.child_window(title=control_name, control_type="Edit")
        ctrl.set_edit_text(text)
        return {"success": True, "typed": text, "into": control_name}
    except Exception as e:
        return {"success": False, "error": str(e)}


def focus_window(app_title: str) -> dict:
    """Bring a window to the foreground."""
    try:
        from pywinauto import Desktop
        app = Desktop(backend="uia").window(title_re=f".*{app_title}.*", found_index=0)
        app.set_focus()
        return {"success": True, "focused": app_title}
    except Exception as e:
        return {"success": False, "error": str(e)}


def open_app(executable: str) -> dict:
    """
    Launch a desktop application by executable name or path.
    e.g. "notepad.exe", "calc.exe"
    """
    try:
        import subprocess
        subprocess.Popen(executable)
        time.sleep(1.5)  # give app time to open
        return {"success": True, "launched": executable}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_focused_control_text(app_title: str) -> str:
    """Read the text of the currently focused control in a window."""
    try:
        from pywinauto import Desktop
        app = Desktop(backend="uia").window(title_re=f".*{app_title}.*", found_index=0)
        focused = app.get_focus()
        return focused.window_text() if focused else "(no focused control)"
    except Exception as e:
        return f"(error: {e})"