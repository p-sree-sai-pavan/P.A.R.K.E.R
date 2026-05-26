# ears.py — Microphone → Text
# Uses: faster-whisper (transcription) + silero VAD (auto-stop on silence)

import os
import time
import tempfile
import queue
import threading
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


class ContinuousVoiceListener:
    """
    A continuous background recorder that listens for Silero VAD triggers.
    Fires speech_detected_callback immediately on speech start (barge-in).
    Puts transcribed human speech into input_queue on speech end.
    """
    def __init__(self, input_queue: queue.Queue, speech_detected_callback):
        self.input_queue = input_queue
        self.speech_detected_callback = speech_detected_callback
        self.running = False
        self.thread = None
        self.stream = None
        
    def start(self):
        _load_models()
        self.running = True
        self.thread = threading.Thread(target=self._run, name="VoiceListenerThread", daemon=True)
        self.thread.start()
        
    def stop(self):
        self.running = False
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
            
    def _run(self):
        print("🎙️ Continuous Voice Listener Active (Silence auto-detection).")
        
        chunk_size = 512
        audio_buffer = []
        is_speaking = False
        silence_start = None
        
        q = queue.Queue()
        
        def callback(indata, frames, time_info, status):
            if status:
                pass
            q.put(indata.copy())
            
        try:
            self.stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=chunk_size,
                callback=callback
            )
            self.stream.start()
        except Exception as e:
            print(f"[Voice Input] Failed to open microphone input stream: {e}")
            self.running = False
            return

        # Pre-roll buffer to keep ~0.5s of history
        preroll_len = int(0.5 * SAMPLE_RATE / chunk_size)
        preroll_buffer = []
        
        from silero_vad import get_speech_timestamps
        
        while self.running:
            try:
                chunk = q.get(timeout=0.1)
            except queue.Empty:
                continue
                
            chunk_flat = chunk.flatten()
            chunk_float = chunk_flat.astype(np.float32) / 32768.0
            
            timestamps = get_speech_timestamps(
                chunk_float,
                _vad_model,
                sampling_rate=SAMPLE_RATE
            )
            
            has_speech = len(timestamps) > 0
            
            if has_speech:
                if not is_speaking:
                    is_speaking = True
                    silence_start = None
                    if self.speech_detected_callback:
                        self.speech_detected_callback()
                    # Initialize speech recording buffer with preroll history
                    audio_buffer = []
                    for pr in preroll_buffer:
                        audio_buffer.extend(pr)
                audio_buffer.extend(chunk_flat)
            else:
                if is_speaking:
                    audio_buffer.extend(chunk_flat)
                    if silence_start is None:
                        silence_start = time.time()
                    elif time.time() - silence_start >= 1.0:  # 1.0s silence threshold
                        speech_audio = np.array(audio_buffer, dtype=np.int16)
                        # Process speech asynchronously so VAD loop doesn't block during Whisper transcription
                        threading.Thread(
                            target=self._process_recorded_speech,
                            args=(speech_audio,),
                            daemon=True
                        ).start()
                        # Reset VAD state
                        is_speaking = False
                        audio_buffer = []
                        silence_start = None
                else:
                    preroll_buffer.append(chunk_flat)
                    if len(preroll_buffer) > preroll_len:
                        preroll_buffer.pop(0)
                        
    def _process_recorded_speech(self, audio_data):
        if len(audio_data) < SAMPLE_RATE * 0.5:
            # Ignore extremely short noises/clicks
            return
            
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav_write(f.name, SAMPLE_RATE, audio_data)
                temp_path = f.name
                
            segments, _ = _whisper.transcribe(temp_path, language="en")
            text = " ".join(seg.text for seg in segments).strip()
            
            try:
                os.unlink(temp_path)
            except Exception:
                pass
                
            if text:
                print(f"\n[Voice Input] You said: {text}")
                self.input_queue.put({"type": "voice", "text": text})
        except Exception as e:
            print(f"[Voice Input Error] Transcription failed: {e}")