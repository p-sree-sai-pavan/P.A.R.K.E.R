# test_chatterbox.py
import torchaudio as ta
from chatterbox.tts import ChatterboxTTS

model = ChatterboxTTS.from_pretrained(device="cuda")
wav = model.generate("Hello Pavan, I am Parker.")
ta.save("test.wav", wav, model.sr)
print("Done — check test.wav")