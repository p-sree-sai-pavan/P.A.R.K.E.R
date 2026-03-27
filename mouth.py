# mouth.py — Text → Speech

import re
import pyttsx3
import threading
import queue

_q    = queue.Queue()
_stop = threading.Event()


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
    try:
        engine = pyttsx3.init()
        engine.setProperty("rate", 175)
        engine.setProperty("volume", 1.0)
    except Exception as e:
        print(f"TTS Init Error: {e}")
        return

    while True:
        text = _q.get()
        if text is None:
            break

        # S5 fix: discard queued items if stop was requested
        if _stop.is_set():
            continue

        try:
            _stop.clear()
            engine.say(_clean(text))
            engine.runAndWait()
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
    try:
        # Re-init engine to force-stop current utterance
        engine = pyttsx3.init()
        engine.stop()
    except Exception:
        pass


_t = threading.Thread(target=_tts_worker, daemon=True)
_t.start()