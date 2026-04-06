import wave
import io
import os

fallback_dir = os.path.join(os.path.dirname(__file__), "assets/fallbacks")
for f in os.listdir(fallback_dir):
    if f.endswith('.wav'):
        with wave.open(os.path.join(fallback_dir, f)) as wav:
            print(f"{f}: width={wav.getsampwidth()}, rate={wav.getframerate()}, channels={wav.getnchannels()}, comptype={wav.getcomptype()}")
