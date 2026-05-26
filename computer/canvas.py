import os
import json
import time
from pathlib import Path

def get_openclaw_state_dir() -> Path:
    """Resolve the active OpenClaw state directory from env or defaults."""
    state_dir = os.environ.get("OPENCLAW_STATE_DIR")
    if state_dir:
        return Path(state_dir)
        
    # Check defaults
    home = Path.home()
    dev_path = home / ".openclaw-dev"
    prod_path = home / ".openclaw"
    
    if dev_path.exists():
        return dev_path
    return prod_path

def wrap_premium_html(title: str, content_html: str) -> str:
    """Wrap content in a high-fidelity JARVIS-style dashboard HTML page."""
    current_time_str = time.strftime("%Y-%m-%d %H:%M:%S")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&family=Space+Mono&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-color: #0b0f19;
            --card-bg: rgba(17, 24, 39, 0.7);
            --accent-cyan: #06b6d4;
            --accent-blue: #3b82f6;
            --accent-glow: rgba(6, 182, 212, 0.15);
            --border-color: rgba(255, 255, 255, 0.08);
            --text-primary: #f3f4f6;
            --text-secondary: #9ca3af;
        }}
        body {{
            background: linear-gradient(135deg, #090d16 0%, #111827 100%);
            color: var(--text-primary);
            font-family: 'Outfit', sans-serif;
            margin: 0;
            padding: 24px;
            min-height: 100vh;
            box-sizing: border-box;
        }}
        .header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 12px;
            margin-bottom: 24px;
        }}
        .title {{
            font-size: 20px;
            font-weight: 600;
            color: var(--accent-cyan);
            text-transform: uppercase;
            letter-spacing: 1.5px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .title::before {{
            content: '';
            display: inline-block;
            width: 8px;
            height: 8px;
            background-color: var(--accent-cyan);
            border-radius: 50%;
            box-shadow: 0 0 8px var(--accent-cyan);
        }}
        .timestamp {{
            font-family: 'Space Mono', monospace;
            font-size: 11px;
            color: var(--text-secondary);
        }}
        .card {{
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
            backdrop-filter: blur(10px);
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
            margin-bottom: 16px;
            transition: all 0.3s ease;
        }}
        .card:hover {{
            border-color: rgba(6, 182, 212, 0.3);
            box-shadow: 0 4px 25px var(--accent-glow);
        }}
        h2 {{
            font-size: 16px;
            font-weight: 600;
            margin-top: 0;
            margin-bottom: 12px;
            color: #ffffff;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            padding-bottom: 8px;
        }}
        .status-pill {{
            display: inline-flex;
            align-items: center;
            padding: 4px 8px;
            border-radius: 9999px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
        }}
        .status-active {{
            background-color: rgba(16, 185, 129, 0.1);
            color: #10b981;
            border: 1px solid rgba(16, 185, 129, 0.2);
        }}
        .status-paused {{
            background-color: rgba(245, 158, 11, 0.1);
            color: #f59e0b;
            border: 1px solid rgba(245, 158, 11, 0.2);
        }}
        .status-completed {{
            background-color: rgba(59, 130, 246, 0.1);
            color: #3b82f6;
            border: 1px solid rgba(59, 130, 246, 0.2);
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 16px;
        }}
        ul {{
            padding-left: 20px;
            margin: 8px 0;
        }}
        li {{
            margin-bottom: 6px;
            color: var(--text-secondary);
        }}
        strong {{
            color: #ffffff;
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="title">{title}</div>
        <div class="timestamp">JARVIS SYSTEM LOG // {current_time_str}</div>
    </div>
    <div class="content">
        {content_html}
    </div>
</body>
</html>"""

def render_canvas_doc(doc_id: str, title: str, html_body: str, height: int = 450) -> str:
    """Create a canvas HTML bundle and manifest under the active state dir.
    
    Returns the [embed] shortcode for final output injection.
    """
    state_dir = get_openclaw_state_dir()
    doc_dir = state_dir / "canvas" / "documents" / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    
    # Wrap in premium JARVIS layout
    full_html = wrap_premium_html(title, html_body)
    
    # Write index.html
    html_file = doc_dir / "index.html"
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(full_html)
        
    # Write manifest.json
    manifest = {
        "id": doc_id,
        "kind": "html_bundle",
        "title": title,
        "preferredHeight": height,
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "entryUrl": f"/__openclaw__/canvas/documents/{doc_id}/index.html",
        "localEntrypoint": "index.html",
        "assets": []
    }
    manifest_file = doc_dir / "manifest.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        
    print(f"[Canvas] Rendered document '{doc_id}' under {doc_dir.resolve()}")
    return f'[embed ref="{doc_id}" title="{title}" height="{height}" /]'
