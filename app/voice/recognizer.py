# recognizer.py

import os
import queue
import sounddevice as sd
import json
from vosk import Model, KaldiRecognizer

model_path = "app/voice/models/vosk-model-small-en-us-0.15"

def recognize_command_from_mic():
    if not os.path.exists(model_path):
        raise FileNotFoundError("Vosk model not found at: " + model_path)

    model = Model(model_path)
    recognizer = KaldiRecognizer(model, 16000)
    q = queue.Queue()

    def callback(indata, frames, time, status):
        q.put(bytes(indata))

    with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype='int16',
                           channels=1, callback=callback):
        print("🎤 Listening... Please speak")
        while True:
            data = q.get()
            if recognizer.AcceptWaveform(data):
                result = json.loads(recognizer.Result())
                text = result.get("text", "")
                print("✅ You said:", text)
                return text
