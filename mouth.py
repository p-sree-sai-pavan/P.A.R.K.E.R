# Remove RealtimeTTS imports and replace with:
import re
import io
import queue
import threading
import requests
import sounddevice as sd
import soundfile as sf

CHATTERBOX_URL = "http://localhost:8004/tts"

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
        response = requests.post(
            CHATTERBOX_URL,
            json={
                "text": text,
                "language": "en",
                "voice_mode": "clone",
                "reference_audio_filename": "reference.wav",
            },
            timeout=60,
        )
        if response.status_code != 200:
            print(f"[TTS] Error: {response.status_code}")
            return
        audio_bytes = io.BytesIO(response.content)
        data, samplerate = sf.read(audio_bytes, dtype="float32")
        if not _stop.is_set():
            sd.play(data, samplerate)
            sd.wait()
    except requests.exceptions.ConnectionError:
        print("[TTS] Chatterbox not running.")
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