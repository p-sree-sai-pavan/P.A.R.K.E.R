# ears.py — Microphone → Text
# Uses: faster-whisper (transcription) + silero VAD (auto-stop on silence)

import tempfile
import numpy as np
import sounddevice as sd
from scipy.io.wavfile import write as wav_write

SAMPLE_RATE = 16000
MAX_SECONDS = 30

# S1 fix: lazy load — models only loaded on first voice use, not at import time
_whisper   = None
_vad_model = None


def _load_models():
    global _whisper, _vad_model
    if _whisper is None:
        from faster_whisper import WhisperModel
        print("Loading Whisper model...")
        _whisper = WhisperModel("small", device="cpu", compute_type="int8")
    if _vad_model is None:
        from silero_vad import load_silero_vad
        print("Loading VAD model...")
        _vad_model = load_silero_vad()


def listen() -> str:
    """
    Records mic until silence for ~1 second.
    Returns transcribed text, or "" if nothing captured.
    """
    _load_models()  # no-op after first call

    print("🎙️  Listening... (speak now, stops when you go silent)")

    audio = sd.rec(
        int(MAX_SECONDS * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16"
    )

    import time
    CHUNK         = int(0.5 * SAMPLE_RATE)
    silence_count = 0
    SILENCE_LIMIT = 2

    start = time.time()
    while True:
        elapsed = int((time.time() - start) * SAMPLE_RATE)
        if elapsed < CHUNK:
            time.sleep(0.1)
            continue

        chunk       = audio[max(0, elapsed - CHUNK):elapsed].flatten()
        chunk_float = chunk.astype(np.float32) / 32768.0

        from silero_vad import get_speech_timestamps
        timestamps = get_speech_timestamps(
            chunk_float,
            _vad_model,
            sampling_rate=SAMPLE_RATE
        )

        if len(timestamps) == 0:
            silence_count += 1
        else:
            silence_count = 0

        if silence_count >= SILENCE_LIMIT:
            sd.stop()
            # S2 fix: clamp to 0 so we never get a negative index
            trim_point  = max(0, elapsed - (CHUNK * SILENCE_LIMIT))
            final_audio = audio[:trim_point]
            break

        if time.time() - start >= MAX_SECONDS:
            sd.stop()
            final_audio = audio[:elapsed]
            break

        time.sleep(0.1)

    # S2 fix: guard against empty audio (silence from the start)
    if len(final_audio) == 0:
        print("No audio captured.")
        return ""

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_write(f.name, SAMPLE_RATE, final_audio)
        temp_path = f.name

    segments, _ = _whisper.transcribe(temp_path, language="en")
    text        = " ".join(seg.text for seg in segments).strip()

    print(f"You said: {text}")
    return text