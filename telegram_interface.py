"""
telegram_interface.py — Telegram Bot interface for Parker AI
Run this instead of main.py to access Parker from anywhere via Telegram.

Setup:
1. Create bot via @BotFather → get token
2. Add TELEGRAM_BOT_TOKEN=your_token to .env
3. Add TELEGRAM_ALLOWED_USER=your_telegram_user_id to .env (security)
4. pip install python-telegram-bot
5. python telegram_interface.py
"""

import warnings
warnings.filterwarnings("ignore")

import os
import logging
import tempfile
import threading
import builtins
from datetime import datetime

# ── Silence background thread prints ──────────────────────────────────────────
_original_print = builtins.print

def thread_safe_print(*args, **kwargs):
    if threading.current_thread().name != "MainThread":
        msg = " ".join(str(a) for a in args)
        if any(tag in msg for tag in ("[Facts]", "[Profile]", "[Projects]", "[Rollup]", "[Episodes]")):
            return
    _original_print(*args, **kwargs)

builtins.print = thread_safe_print

from dotenv import load_dotenv
load_dotenv()

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ChatAction

from langchain_core.messages import HumanMessage

from graph import build_graph
from config import DEFAULT_USER_ID, DEFAULT_THREAD_ID, get_config, CHAT_LLM_MODEL
from database import create_store, create_checkpointer, setup_database, close_connections
from memory.rollup import refresh_active_rollups, rollup_if_needed
from memory.facts import archive_stale_facts
from memory.projects import archive_completed_projects
from memory.episodes import normalize_chat_summaries, write_chat_turn_async
from memory.utils import wait_for_background_jobs

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ── Config ─────────────────────────────────────────────────────────────────────

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOWED_USER = os.getenv("TELEGRAM_ALLOWED_USER", "")  # your telegram user_id (int as string)

if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN not set in .env")

USER_ID = DEFAULT_USER_ID
SESSION_THREAD_ID = f"{DEFAULT_THREAD_ID}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
config = get_config(USER_ID, SESSION_THREAD_ID)

# Global graph (initialized in main)
graph = None
store = None


# ── Security ───────────────────────────────────────────────────────────────────

def is_allowed(update: Update) -> bool:
    """Only respond to the configured user. Leave TELEGRAM_ALLOWED_USER empty to allow anyone."""
    if not ALLOWED_USER:
        return True
    return str(update.effective_user.id) == ALLOWED_USER


# ── Core ask ───────────────────────────────────────────────────────────────────

def ask(prompt: str) -> str:
    try:
        result = graph.invoke(
            {"messages": [HumanMessage(content=prompt)]},
            config,
        )
        last_msg = result["messages"][-1]
        if hasattr(last_msg, "content"):
            return last_msg.content
        if isinstance(last_msg, dict):
            return last_msg.get("content", "")
        return ""
    except Exception as e:
        err = str(e)
        if "429" in err or "rate_limit" in err.lower():
            return "⚠️ Groq rate limit hit. Wait a moment and try again."
        logger.error(f"ask() failed: {e}")
        return f"⚠️ Error: {err}"


# ── Handlers ───────────────────────────────────────────────────────────────────

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    await update.message.reply_text(
        "Parker online.\n\n"
        "Commands:\n"
        "/profile — show memory profile\n"
        "/facts — list stored facts\n"
        "/projects — list active projects\n"
        "/clear — clear session context\n\n"
        "Send text or a voice message."
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return

    user_input = update.message.text.strip()
    if not user_input:
        return

    await update.message.chat.send_action(ChatAction.TYPING)

    response = ask(user_input)


    # Telegram has 4096 char limit per message
    if len(response) <= 4096:
        await update.message.reply_text(response, parse_mode="Markdown")
    else:
        # Split on double newline to avoid breaking mid-sentence
        chunks = _split_message(response, 4096)
        for chunk in chunks:
            await update.message.reply_text(chunk, parse_mode="Markdown")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Download voice message → transcribe via Whisper → ask Parker."""
    if not is_allowed(update):
        return

    await update.message.chat.send_action(ChatAction.TYPING)

    try:
        voice_file = await update.message.voice.get_file()

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            tmp_path = f.name

        await voice_file.download_to_drive(tmp_path)

        # Lazy load Whisper (same as ears.py)
        from ears import _load_models
        import ears
        _load_models()

        segments, _ = ears._whisper.transcribe(tmp_path, language="en")
        user_input = " ".join(seg.text for seg in segments).strip()

        os.unlink(tmp_path)

        if not user_input:
            await update.message.reply_text("Couldn't transcribe that. Try again.")
            return

        # Echo transcription so user knows what was heard
        await update.message.reply_text(f"_{user_input}_", parse_mode="Markdown")

        response = ask(user_input)

        await update.message.reply_text(response, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Voice handling failed: {e}")
        await update.message.reply_text(f"⚠️ Voice error: {e}")


async def handle_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    from memory.profile import load_profile
    prof = load_profile(store, USER_ID)
    if not prof:
        await update.message.reply_text("No profile saved yet.")
        return
    lines = [f"*{k.replace('_', ' ')}:* {v}" for k, v in prof.items()]
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def handle_facts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    from memory.facts import full_scan, NAMESPACE
    items = full_scan(store, NAMESPACE(USER_ID))
    if not items:
        await update.message.reply_text("No facts stored yet.")
        return
    icons = {"critical": "🔴", "high": "🟠", "normal": "⚪", "low": "⚫"}
    lines = []
    for i in sorted(items, key=lambda x: ["critical","high","normal","low"].index(x.value.get("importance","normal"))):
        imp = i.value.get("importance", "normal")
        lines.append(f"{icons.get(imp,'⚪')} *{i.key}:* {i.value.get('content','')}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def handle_projects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    from memory.projects import load_active_projects
    projs = load_active_projects(store, USER_ID)
    if not projs:
        await update.message.reply_text("No active projects.")
        return
    lines = []
    for p in projs:
        v = p.value
        lines.append(f"*{v.get('name', p.key)}* [{v.get('status','active')}]")
        if v.get("summary"):
            lines.append(f"  {v['summary']}")
        if v.get("stack"):
            lines.append(f"  Stack: {', '.join(v['stack'])}")
        lines.append("")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def handle_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    await update.message.reply_text("Context cleared. Starting fresh.")


async def handle_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    await update.message.reply_text("Unknown command. Send /start to see available commands.")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _split_message(text: str, limit: int) -> list[str]:
    chunks = []
    while len(text) > limit:
        split_at = text.rfind("\n\n", 0, limit)
        if split_at == -1:
            split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at].strip())
        text = text[split_at:].strip()
    if text:
        chunks.append(text)
    return chunks


# ── Startup / Shutdown ─────────────────────────────────────────────────────────

def session_start():
    logger.info("Running session start hooks...")
    normalize_chat_summaries(store, USER_ID)
    rollup_if_needed(store, USER_ID)
    archive_stale_facts(store, USER_ID)
    archive_completed_projects(store, USER_ID)
    logger.info("Startup hooks complete.")


def session_end():
    logger.info("Refreshing summary tree...")
    refresh_active_rollups(store, USER_ID)
    store.put(("user", USER_ID, "state"), "last_session", {
        "date": datetime.now().strftime("%Y-%m-%d")
    })
    logger.info("Session state saved.")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    global graph, store

    store = create_store()
    checkpointer = create_checkpointer()
    setup_database(store, checkpointer)
    graph = build_graph(store, checkpointer)

    session_start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",    handle_start))
    app.add_handler(CommandHandler("profile",  handle_profile))
    app.add_handler(CommandHandler("facts",    handle_facts))
    app.add_handler(CommandHandler("projects", handle_projects))
    app.add_handler(CommandHandler("clear",    handle_clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.COMMAND, handle_unknown))

    logger.info(f"Parker Telegram bot running — model: {CHAT_LLM_MODEL}")
    logger.info("Press Ctrl+C to stop.")

    try:
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    finally:
        logger.info("Shutting down...")
        wait_for_background_jobs()
        session_end()
        close_connections()


if __name__ == "__main__":
    main()