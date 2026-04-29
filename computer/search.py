"""
computer/search.py — Web search engine for Parker AI

Two-layer architecture:
  Layer 1: SearXNG (self-hosted, localhost:8080) — instant, unlimited, aggregates 10+ engines
  Layer 2: Playwright — full page extraction for deep=true or when snippets are thin

Parker signals search via:
  <computer_action>{"mode": "web_search", "query": "...", "deep": false}</computer_action>
"""

import os
import requests
from typing import Optional

SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8080/search")
MAX_RESULTS  = 8       # snippets returned to Parker
MAX_DEEP     = 3       # max pages fetched when deep=True
SNIPPET_MIN  = 80      # chars — if avg snippet below this, auto-upgrade to deep


# ── Public API ─────────────────────────────────────────────────────────────────

def web_search(query: str, deep: bool = False, category: str = "general") -> str:
    """
    Search the web and return a formatted result string for Parker.

    Args:
        query:    Natural language or keyword query.
        deep:     If True, fetch full page content for top results via Playwright.
        category: SearXNG category — "general" | "news" | "science" | "it" | "social media"

    Returns:
        Formatted string: sources + snippets (+ full content if deep).
    """
    results = _searxng_query(query, category=category)

    if not results:
        return f"[Search] No results found for: {query}"

    # Auto-upgrade to deep if snippets are very thin
    avg_snippet_len = sum(len(r.get("content", "")) for r in results) / len(results)
    if not deep and avg_snippet_len < SNIPPET_MIN:
        deep = True

    if deep:
        return _deep_results(query, results)
    else:
        return _format_snippets(query, results)


# ── SearXNG ────────────────────────────────────────────────────────────────────

def _searxng_query(query: str, category: str = "general") -> list[dict]:
    """
    Query local SearXNG instance. Returns list of result dicts.
    Each dict has: title, url, content (snippet), engine, score.
    """
    try:
        resp = requests.get(
            SEARXNG_URL,
            params={
                "q":        query,
                "format":   "json",
                "categories": category,
                "language": "en",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data    = resp.json()
        results = data.get("results", [])
        return results[:MAX_RESULTS]

    except requests.exceptions.ConnectionError:
        return _fallback_ddg(query)
    except Exception as e:
        print(f"[Search] SearXNG query failed: {e}")
        return _fallback_ddg(query)


def _fallback_ddg(query: str) -> list[dict]:
    """
    Fallback to duckduckgo-search if SearXNG is unreachable.
    Normalises output to same shape as SearXNG results.
    """
    try:
        from duckduckgo_search import DDGS
        raw = DDGS().text(query, max_results=MAX_RESULTS, backend="lite")
        return [
            {
                "title":   r.get("title", ""),
                "url":     r.get("href", ""),
                "content": r.get("body", ""),
                "engine":  "duckduckgo",
            }
            for r in (raw or [])
        ]
    except Exception as e:
        print(f"[Search] DDG fallback also failed: {e}")
        return []


# ── Formatting ─────────────────────────────────────────────────────────────────

def _format_snippets(query: str, results: list[dict]) -> str:
    """Format SearXNG snippets into a clean string for Parker's context."""
    lines = [f"Search results for: {query}\n"]

    for i, r in enumerate(results, 1):
        title   = r.get("title", "Untitled")
        url     = r.get("url", "")
        snippet = (r.get("content") or r.get("snippet") or "").strip()
        engine  = r.get("engine", "")

        lines.append(f"[{i}] {title}")
        lines.append(f"    URL: {url}")
        if snippet:
            # Truncate very long snippets
            if len(snippet) > 400:
                snippet = snippet[:397] + "..."
            lines.append(f"    {snippet}")
        if engine:
            lines.append(f"    via {engine}")
        lines.append("")

    return "\n".join(lines).strip()


def _deep_results(query: str, results: list[dict]) -> str:
    """
    Fetch full page content for top results using Playwright.
    Falls back to snippet if Playwright fails for a given URL.
    """
    lines = [f"Deep search results for: {query}\n"]

    top = results[:MAX_DEEP]
    remaining = results[MAX_DEEP:]

    for i, r in enumerate(top, 1):
        title = r.get("title", "Untitled")
        url   = r.get("url", "")
        lines.append(f"[{i}] {title}")
        lines.append(f"    URL: {url}")

        content = _fetch_page_content(url)
        if content:
            lines.append(f"    FULL CONTENT:\n{_indent(content)}")
        else:
            snippet = (r.get("content") or r.get("snippet") or "").strip()
            if snippet:
                lines.append(f"    {snippet}")
        lines.append("")

    # Append remaining as snippets only
    if remaining:
        lines.append("Additional results (snippets):\n")
        for i, r in enumerate(remaining, len(top) + 1):
            title   = r.get("title", "Untitled")
            url     = r.get("url", "")
            snippet = (r.get("content") or r.get("snippet") or "").strip()
            lines.append(f"[{i}] {title}  —  {url}")
            if snippet:
                snippet_short = snippet[:200] + "..." if len(snippet) > 200 else snippet
                lines.append(f"    {snippet_short}")
            lines.append("")

    return "\n".join(lines).strip()


def _fetch_page_content(url: str) -> Optional[str]:
    """
    Fetch full visible text from a URL using Playwright.
    Returns None on failure so caller can fall back to snippet.
    """
    try:
        from computer.browser import _get_page, get_page_text
        _get_page(url)
        text = get_page_text()
        # Truncate to 2500 chars per page — plenty for Parker
        if len(text) > 2500:
            text = text[:2497] + "..."
        return text if len(text) > 100 else None
    except Exception as e:
        print(f"[Search] Playwright fetch failed for {url}: {e}")
        return None


def _indent(text: str, prefix: str = "    ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())