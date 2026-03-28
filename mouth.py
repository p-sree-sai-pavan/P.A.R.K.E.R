# mouth.py — Text → Speech

import re
import sys
import pyttsx3
import threading
import queue

_q    = queue.Queue()
_stop = threading.Event()
_engine_lock = threading.Lock()
_current_engine = None


def _clean(text: str) -> str:
    """M1 fix: strip all common markdown before speaking."""
    text = re.sub(r"```[\s\S]*?```", "", text)   # code blocks
    text = re.sub(r"`[^`]*`", "", text)           # inline code
    text = re.sub(r"#{1,6}\s*", "", text)         # headers
    text = re.sub(r"\*{1,3}([^*]*)\*{1,3}", r"\1", text)  # bold/italic
    text = re.sub(r"_{1,3}([^_]*)_{1,3}", r"\1", text)    # underline
    text = re.sub(r"^>\s*", "", text, flags=re.MULTILINE)  # blockquotes
    text = re.sub(r"^-{3,}$", "", text, flags=re.MULTILINE)  # dividers
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # links → text only
    return text.strip()


def _tts_worker():
    while True:
        text = _q.get()
        if text is None:
            break

        # S5 fix: discard queued items if stop was requested
        if _stop.is_set():
            _stop.clear()
            continue

        try:
            cleaned = _clean(text)
            if not cleaned:
                continue

            _stop.clear()
            _speak_once(cleaned)
        except Exception as e:
            print(f"TTS Speech Error: {e}")


def speak(text: str):
    """Queue text for speech. Non-blocking."""
    _q.put(text)


def stop_speaking():
    """
    S5 fix: interrupt current speech and discard all queued items.
    Call this when user submits a new message or hits Stop.
    """
    _stop.set()
    # Drain the queue
    while not _q.empty():
        try:
            _q.get_nowait()
        except Exception:
            break
    with _engine_lock:
        engine = _current_engine
    if engine is not None:
        try:
            engine.stop()
        except Exception:
            pass


def _speak_once(text: str):
    global _current_engine

    pythoncom = None
    if sys.platform == "win32":
        try:
            import pythoncom as _pythoncom
            pythoncom = _pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pythoncom = None

    engine = None
    try:
        engine = pyttsx3.init()
        engine.setProperty("rate", 175)
        engine.setProperty("volume", 1.0)

        with _engine_lock:
            _current_engine = engine

        engine.say(text)
        engine.runAndWait()
    finally:
        if engine is not None:
            try:
                engine.stop()
            except Exception:
                pass

        with _engine_lock:
            if _current_engine is engine:
                _current_engine = None

        if pythoncom is not None:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass


_t = threading.Thread(target=_tts_worker, daemon=True)
_t.start()
