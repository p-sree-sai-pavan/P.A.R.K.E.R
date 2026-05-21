# mouth.py — Kokoro TTS (replaces Chatterbox)
# pip install kokoro>=0.9.4 sounddevice soundfile misaki[en]
# Windows: also install espeak-ng from https://github.com/espeak-ng/espeak-ng/releases

import re
import queue
import threading
import numpy as np
import sounddevice as sd

# ── Voice options (pick one) ───────────────────────────────────────────────────
# American English females : af_heart, af_bella, af_nicole, af_sarah, af_sky
# American English males   : am_adam, am_michael
# British English females  : bf_emma, bf_isabella
# British English males    : bm_george, bm_lewis
VOICE    = "bm_george"   # British English male voice matching butler persona
SPEED    = 1.0
LANG     = "b"         # 'a' = American English, 'b' = British English

# ── Lazy-load pipeline (first speak() call only) ──────────────────────────────
_pipeline = None
_pipeline_lock = threading.Lock()

def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        with _pipeline_lock:
            if _pipeline is None:
                from kokoro import KPipeline
                print("[TTS] Loading Kokoro pipeline...")
                _pipeline = KPipeline(lang_code=LANG)
                print("[TTS] Kokoro ready.")
    return _pipeline


# ── Queue-based worker (same pattern as before) ───────────────────────────────
_q    = queue.Queue()
_stop = threading.Event()


def _clean(text: str) -> str:
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`]*`", "", text)
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"\*{1,3}([^*]*)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,3}([^_]*)_{1,3}", r"\1", text)
    text = re.sub(r"^>\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^-{3,}$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _speak_once(text: str):
    try:
        pipeline = _get_pipeline()
        generator = pipeline(text, voice=VOICE, speed=SPEED)

        for _, _, audio in generator:
            if _stop.is_set():
                break
            # audio is a numpy float32 array at 24000 Hz
            sd.play(audio, samplerate=24000)
            sd.wait()

    except Exception as e:
        print(f"[TTS] Error: {e}")


def _tts_worker():
    while True:
        text = _q.get()
        if text is None:
            break
        if _stop.is_set():
            _stop.clear()
            continue
        cleaned = _clean(text)
        if cleaned:
            _stop.clear()
            _speak_once(cleaned)


def speak(text: str):
    _q.put(text)


def stop_speaking():
    _stop.set()
    while not _q.empty():
        try:
            _q.get_nowait()
        except Exception:
            break
    sd.stop()


_t = threading.Thread(target=_tts_worker, daemon=True)
_t.start()