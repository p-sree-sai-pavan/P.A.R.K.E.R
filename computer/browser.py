"""
computer/browser.py — Playwright DOM controller for Parker AI

Gives Parker the ability to control a browser via DOM inspection.
No screenshots. Pure structured data — fast, cheap, reliable.
"""

import json
from typing import Optional

# Lazy-loaded to avoid import cost when feature is disabled
_playwright_cm = None
_browser = None
_page = None


def _get_page(url: Optional[str] = None):
    """
    Lazily initialize Playwright and return a page.
    Reuses existing browser session if already open.
    """
    global _playwright_cm, _browser, _page

    from playwright.sync_api import sync_playwright

    if _playwright_cm is None:
        _playwright_cm = sync_playwright().__enter__()
        _browser = _playwright_cm.chromium.launch(headless=False)

    if _page is None or _page.is_closed():
        _page = _browser.new_page()

    if url:
        _page.goto(url, wait_until="domcontentloaded", timeout=15000)

    return _page


def navigate(url: str) -> dict:
    """Navigate to a URL and return page title + current URL."""
    try:
        page = _get_page(url)
        return {
            "success": True,
            "title": page.title(),
            "url": page.url,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_interactive_elements() -> list[dict]:
    """
    Extract all interactive elements from the current page as structured data.
    Returns buttons, inputs, links, selects — the full actionable DOM.
    """
    try:
        page = _get_page()
        elements = page.evaluate("""
            () => {
                const results = [];
                const selectors = ['button', 'input', 'a', 'select', 'textarea', '[role="button"]', '[role="link"]'];
                selectors.forEach(selector => {
                    document.querySelectorAll(selector).forEach((el, idx) => {
                        const rect = el.getBoundingClientRect();
                        if (rect.width === 0 || rect.height === 0) return;
                        results.push({
                            tag: el.tagName.toLowerCase(),
                            type: el.type || null,
                            text: (el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || '').trim().slice(0, 80),
                            id: el.id || null,
                            name: el.name || null,
                            href: el.href || null,
                            role: el.getAttribute('role') || null,
                            selector: selector,
                            index: idx,
                        });
                    });
                });
                return results;
            }
        """)
        # Filter out elements with no useful text
        return [e for e in elements if e.get("text") or e.get("id") or e.get("name")]
    except Exception as e:
        return [{"error": str(e)}]


def get_page_text() -> str:
    """Extract visible text content from the current page for Parker to read."""
    try:
        page = _get_page()
        text = page.evaluate("""
            () => {
                const clone = document.body.cloneNode(true);
                clone.querySelectorAll('script, style, nav, footer, iframe').forEach(el => el.remove());
                return clone.innerText.replace(/\\s+/g, ' ').trim().slice(0, 3000);
            }
        """)
        return text
    except Exception as e:
        return f"(Could not read page: {e})"


def click_element(text: str = None, selector: str = None, element_id: str = None) -> dict:
    """
    Click an element by visible text, CSS selector, or ID.
    Tries each strategy in order until one works.
    """
    page = _get_page()
    strategies = []

    if text:
        strategies.append(("text", lambda: page.get_by_text(text, exact=False).first.click()))
    if element_id:
        strategies.append(("id", lambda: page.locator(f"#{element_id}").click()))
    if selector:
        strategies.append(("selector", lambda: page.locator(selector).first.click()))

    for name, action in strategies:
        try:
            action()
            page.wait_for_load_state("domcontentloaded", timeout=5000)
            return {"success": True, "method": name, "new_url": page.url}
        except Exception as e:
            continue

    return {"success": False, "error": f"Could not click: text={text}, id={element_id}, selector={selector}"}


def type_text(text: str, target_label: str = None, target_id: str = None) -> dict:
    """Type text into an input field identified by label or ID."""
    page = _get_page()

    try:
        if target_id:
            page.locator(f"#{target_id}").fill(text)
        elif target_label:
            page.get_by_label(target_label).fill(text)
        else:
            # Focus the first visible input
            page.locator("input:visible").first.fill(text)
        return {"success": True, "typed": text}
    except Exception as e:
        return {"success": False, "error": str(e)}


def press_key(key: str) -> dict:
    """Press a keyboard key (Enter, Tab, Escape, etc.)."""
    try:
        page = _get_page()
        page.keyboard.press(key)
        return {"success": True, "key": key}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_current_url() -> str:
    """Return the current browser URL."""
    try:
        return _get_page().url
    except Exception:
        return "(browser not open)"


def close_browser():
    """Close the browser session cleanly."""
    global _playwright_cm, _browser, _page
    try:
        if _page and not _page.is_closed():
            _page.close()
        if _browser:
            _browser.close()
        if _playwright_cm:
            _playwright_cm.__exit__(None, None, None)
    except Exception:
        pass
    finally:
        _playwright_cm = None
        _browser = None
        _page = None