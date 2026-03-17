# mouth.py — Text → Speech
# Uses: pyttsx3 (fully local, works on Windows, zero setup)

import pyttsx3

# Load engine ONCE at startup
_engine = pyttsx3.init()
_engine.setProperty("rate", 175)     # 175 words/min = natural speed
_engine.setProperty("volume", 1.0)   # max volume

# Optional — list available voices and pick one
# voices = _engine.getProperty("voices")
# _engine.setProperty("voice", voices[0].id)  # 0 = first voice
# print([v.name for v in voices])              # see all options

def speak(text: str):
    """Speak text out loud. Blocks until done speaking."""
    _engine.say(text)
    _engine.runAndWait()