# mouth.py — Text → Speech
# Uses: pyttsx3 (fully local, works on Windows, zero setup)

import pyttsx3
import threading
import queue

_q = queue.Queue()

def _tts_worker():
    # Initialize engine INSIDE the thread that will use it.
    # Windows COM objects (SAPI5) crash if shared across threads.
    try:
        engine = pyttsx3.init()
        engine.setProperty("rate", 175)     # 175 words/min
        engine.setProperty("volume", 1.0)
    except Exception as e:
        print(f"TTS Init Error: {e}")
        return

    while True:
        text = _q.get()
        if text is None: break
        
        # SAPI5 sometimes gets stuck parsing markdown symbols, so we clean it slightly
        clean_text = text.replace("*", "").replace("#", "").replace("_", "")
        
        try:
            engine.say(clean_text)
            engine.runAndWait()
        except Exception as e:
            print(f"TTS Speech Error: {e}")

# Start the dedicated TTS thread eagerly
_t = threading.Thread(target=_tts_worker, daemon=True)
_t.start()

def speak(text: str):
    """
    Queue text to be spoken out loud. 
    Non-blocking. Thread-safe.
    """
    _q.put(text)