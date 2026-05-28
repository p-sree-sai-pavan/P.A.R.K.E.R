"""
live_voice.py — Gemini Multimodal Live API Voice Session for Parker AI

Replaces the ears.py (Whisper STT) + mouth.py (Kokoro TTS) stack during
Voice Mode with a single low-latency WebSocket session via google-genai.

Architecture:
    ┌─────────────┐        PCM 16kHz         ┌──────────────────────┐
    │ Microphone  │ ──────────────────────▶  │                      │
    │ (sounddevice│                           │  Gemini Live Session │
    │  InputStream│                           │  (WebSocket)         │
    └─────────────┘                           │                      │
                                              │  gemini-2.0-flash-   │
    ┌─────────────┐        PCM 24kHz         │  live-preview        │
    │ Speaker     │ ◀──────────────────────  │                      │
    │ (sounddevice│                           └──────────────────────┘
    │  OutputStream                                    │
    └─────────────┘                     text transcription
                                                       │
                                              ┌────────▼────────┐
                                              │  Parker Memory  │
                                              │  (graph invoke) │
                                              └─────────────────┘

Key features:
  - Automatic VAD (server-side) — user speech triggers response
  - Barge-in support — incoming audio stops when user speaks
  - Input transcription — spoken words are echoed to console
  - Output transcription — Parker's reply text is echoed too
  - Parker's system prompt + full memory context injected as system instruction
  - Graceful stop via asyncio.Event
"""

import asyncio
import queue
import threading
import numpy as np
import sounddevice as sd

from google import genai
from google.genai import types

# ── Config constants ───────────────────────────────────────────────────────────

LIVE_MODEL     = "gemini-2.0-flash-live-preview"
INPUT_RATE     = 16_000   # Hz — native rate for Live API
OUTPUT_RATE    = 24_000   # Hz — Gemini returns 24kHz PCM
CHUNK_FRAMES   = 1_024    # frames per sounddevice callback block (~64ms @16kHz)
MIME_TYPE      = "audio/pcm;rate=16000"

# ── Shared state ───────────────────────────────────────────────────────────────

_live_stop_event: asyncio.Event | None = None
_live_thread:     threading.Thread | None = None


# ── Public API ─────────────────────────────────────────────────────────────────

def start_live_voice_session(
    system_prompt: str,
    on_user_transcript: callable = None,
    on_parker_transcript: callable = None,
    on_session_end: callable = None,
):
    """
    Launch the Gemini Live voice loop in a background daemon thread.

    Args:
        system_prompt:         Full Parker system prompt with memory context injected.
        on_user_transcript:    Called with (str) when user speech is transcribed.
        on_parker_transcript:  Called with (str) when Parker's reply is transcribed.
        on_session_end:        Called with no args when the session closes.
    """
    global _live_stop_event, _live_thread

    stop_event = asyncio.Event()
    _live_stop_event = stop_event

    def _runner():
        asyncio.run(
            _live_session_loop(
                system_prompt=system_prompt,
                stop_event=stop_event,
                on_user_transcript=on_user_transcript,
                on_parker_transcript=on_parker_transcript,
            )
        )
        if on_session_end:
            on_session_end()

    _live_thread = threading.Thread(target=_runner, name="GeminiLiveVoiceThread", daemon=True)
    _live_thread.start()


def stop_live_voice_session():
    """Signal the live voice session to shut down cleanly."""
    global _live_stop_event
    if _live_stop_event is not None:
        # The event lives on the runner thread's loop; set it thread-safely
        _live_stop_event.set()
        _live_stop_event = None


def is_live_session_active() -> bool:
    """Returns True if a live session thread is currently running."""
    return _live_thread is not None and _live_thread.is_alive()


# ── Internal session loop ──────────────────────────────────────────────────────

async def _live_session_loop(
    system_prompt: str,
    stop_event: asyncio.Event,
    on_user_transcript: callable,
    on_parker_transcript: callable,
):
    """Main coroutine that owns the WebSocket session and spawns mic/speaker tasks."""
    import os
    from config import GEMINI_API_KEY

    api_key = GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "")
    client = genai.Client(api_key=api_key)

    session_config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=types.Content(
            parts=[types.Part(text=system_prompt)],
            role="user",
        ),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        # Server-side VAD — model stops when user speaks (barge-in)
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                disabled=False,
            )
        ),
    )

    print("[Live Voice] Connecting to Gemini Live...")

    try:
        async with client.aio.live.connect(model=LIVE_MODEL, config=session_config) as session:
            print("[Live Voice] Session active. Speak now.")

            # Queue bridging sounddevice callback → asyncio send task
            mic_queue: asyncio.Queue[bytes] = asyncio.Queue()

            async with asyncio.TaskGroup() as tg:
                tg.create_task(_mic_sender(session, mic_queue, stop_event),    name="mic_sender")
                tg.create_task(_response_receiver(session, stop_event,
                                                   on_user_transcript,
                                                   on_parker_transcript),      name="receiver")
                tg.create_task(_mic_capture(mic_queue, stop_event),            name="mic_capture")
                tg.create_task(_stop_watcher(session, stop_event),             name="stop_watcher")

    except Exception as e:
        print(f"[Live Voice] Session error: {e}")
    finally:
        print("[Live Voice] Session closed.")


# ── Microphone capture ─────────────────────────────────────────────────────────

async def _mic_capture(mic_queue: asyncio.Queue[bytes], stop_event: asyncio.Event):
    """
    Open a sounddevice InputStream and push raw int16 PCM chunks into mic_queue.
    Uses loop.call_soon_threadsafe so the callback is safe across threads.
    """
    loop = asyncio.get_running_loop()

    def _sd_callback(indata, frames, time_info, status):
        if status:
            pass  # ignore xruns in background
        if not stop_event.is_set():
            raw = indata[:, 0].astype(np.int16).tobytes()
            loop.call_soon_threadsafe(mic_queue.put_nowait, raw)

    stream = sd.InputStream(
        samplerate=INPUT_RATE,
        channels=1,
        dtype="int16",
        blocksize=CHUNK_FRAMES,
        callback=_sd_callback,
    )

    with stream:
        await stop_event.wait()  # keep stream open until stop is signalled


# ── Mic → Gemini sender ────────────────────────────────────────────────────────

async def _mic_sender(
    session,
    mic_queue: asyncio.Queue[bytes],
    stop_event: asyncio.Event,
):
    """Drain mic_queue and stream audio chunks to the Gemini Live session."""
    while not stop_event.is_set():
        try:
            chunk = await asyncio.wait_for(mic_queue.get(), timeout=0.5)
        except asyncio.TimeoutError:
            continue

        await session.send_realtime_input(
            audio=types.Blob(data=chunk, mime_type=MIME_TYPE)
        )


# ── Gemini → Speaker receiver ──────────────────────────────────────────────────

async def _response_receiver(
    session,
    stop_event: asyncio.Event,
    on_user_transcript: callable,
    on_parker_transcript: callable,
):
    """
    Consume server messages:
      - Audio data  → write to sounddevice OutputStream
      - Transcripts → forward to callbacks (console display)
      - Interrupted → stop current playback immediately
    """
    # Audio playback is done through a dedicated OutputStream kept open.
    # We accumulate chunks and write them inline (low latency).
    output_stream = sd.OutputStream(
        samplerate=OUTPUT_RATE,
        channels=1,
        dtype="int16",
    )
    output_stream.start()
    parker_transcript_buf = []
    user_transcript_buf = []

    try:
        async for response in session.receive():
            if stop_event.is_set():
                break

            # ── Barge-in: server signals model was interrupted ─────────────
            if response.server_content and response.server_content.interrupted:
                # Drain the output buffer immediately
                output_stream.stop()
                output_stream.start()
                parker_transcript_buf.clear()
                continue

            # ── Audio chunks from Gemini ───────────────────────────────────
            if (
                response.server_content
                and response.server_content.model_turn
                and response.server_content.model_turn.parts
            ):
                for part in response.server_content.model_turn.parts:
                    if part.inline_data and part.inline_data.mime_type.startswith("audio/"):
                        audio_bytes = part.inline_data.data
                        audio_np = np.frombuffer(audio_bytes, dtype=np.int16)
                        output_stream.write(audio_np)

            # ── Input (user) transcription ─────────────────────────────────
            if response.server_content and response.server_content.input_transcription:
                text = response.server_content.input_transcription.text
                if text:
                    user_transcript_buf.append(text)
                    full = "".join(user_transcript_buf)
                    if on_user_transcript:
                        on_user_transcript(full)

            # ── Output (Parker) transcription ──────────────────────────────
            if response.server_content and response.server_content.output_transcription:
                text = response.server_content.output_transcription.text
                if text:
                    parker_transcript_buf.append(text)
                    full = "".join(parker_transcript_buf)
                    if on_parker_transcript:
                        on_parker_transcript(full)

            # ── Turn complete — flush transcript buffers ────────────────────
            if response.server_content and response.server_content.turn_complete:
                user_transcript_buf.clear()
                parker_transcript_buf.clear()

    finally:
        output_stream.stop()
        output_stream.close()


# ── Stop watcher ───────────────────────────────────────────────────────────────

async def _stop_watcher(session, stop_event: asyncio.Event):
    """When stop_event fires, close the session gracefully."""
    await stop_event.wait()
    try:
        await session.close()
    except Exception:
        pass
