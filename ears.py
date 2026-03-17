# ears.py — Microphone → Text
# Uses: faster-whisper (transcription) + silero VAD (auto-stop on silence)

import tempfile
import numpy as np
import sounddevice as sd
from scipy.io.wavfile import write as wav_write
from faster_whisper import WhisperModel
from silero_vad import load_silero_vad, get_speech_timestamps

# ── Load models ONCE at startup (not on every listen call) ──
print("Loading Whisper model...")
whisper = WhisperModel("small", device="cpu", compute_type="int8")
# small  = good accuracy, ~500MB, works fine on CPU
# tiny   = faster, less accurate
# medium = more accurate, slower

print("Loading VAD model...")
vad_model = load_silero_vad()
# VAD = Voice Activity Detector
# Tells us exactly WHEN you are speaking vs silent
# ~2MB model, runs in <1ms per chunk

SAMPLE_RATE = 16000   # whisper + silero both need 16kHz
MAX_SECONDS = 30      # safety limit — won't record forever

def listen() -> str:
    """
    Records mic until you go silent for ~1 second.
    Returns transcribed text.
    No fixed timer — stops automatically when you stop speaking.
    """
    print("🎙️  Listening... (speak now, stops when you go silent)")

    # Step 1 — Record audio up to MAX_SECONDS
    audio = sd.rec(
        int(MAX_SECONDS * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16"
    )

    # Step 2 — Wait until silence detected
    # We check every 0.5s if user has stopped speaking
    import time
    CHUNK = int(0.5 * SAMPLE_RATE)   # check every 0.5 seconds
    silence_count = 0
    SILENCE_LIMIT = 2   # stop after 2 consecutive silent chunks (~1 second)

    start = time.time()
    while True:
        elapsed = int((time.time() - start) * SAMPLE_RATE)
        if elapsed < CHUNK:
            time.sleep(0.1)
            continue

        # Get audio recorded so far
        chunk = audio[max(0, elapsed - CHUNK):elapsed].flatten()

        # Convert to float for VAD
        chunk_float = chunk.astype(np.float32) / 32768.0

        # Ask VAD: is this chunk speech or silence?
        timestamps = get_speech_timestamps(
            chunk_float,
            vad_model,
            sampling_rate=SAMPLE_RATE
        )

        if len(timestamps) == 0:
            # No speech detected in this chunk
            silence_count += 1
        else:
            # Speech detected — reset silence counter
            silence_count = 0

        # Stop if we've had enough silence
        if silence_count >= SILENCE_LIMIT:
            sd.stop()
            # Trim audio to where silence started
            final_audio = audio[:elapsed - (CHUNK * SILENCE_LIMIT)]
            break

        # Safety — stop at max seconds
        if time.time() - start >= MAX_SECONDS:
            sd.stop()
            final_audio = audio[:elapsed]
            break

        time.sleep(0.1)

    # Step 3 — Save trimmed audio to temp file
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_write(f.name, SAMPLE_RATE, final_audio)
        temp_path = f.name

    # Step 4 — Transcribe with faster-whisper
    segments, _ = whisper.transcribe(temp_path, language="en")
    text = " ".join(seg.text for seg in segments).strip()

    print(f"You said: {text}")
    return text