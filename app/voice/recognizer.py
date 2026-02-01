# recognizer.py

import os
import queue
import json
import wave
import tempfile
from vosk import Model, KaldiRecognizer
from pydub import AudioSegment

model_path = "app/voice/models/vosk-model-small-en-us-0.15"

def recognize_command_from_mic():
    """
    Recognize speech from microphone input.
    Note: Requires sounddevice and PortAudio library to be installed.
    """
    # Import sounddevice only when needed to avoid PortAudio dependency issues
    import sounddevice as sd
    
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


def _convert_to_wav(audio_file_path: str, output_path: str = None) -> str:
    """
    Convert MP3 or M4A file to WAV format suitable for Vosk (16kHz, mono, 16-bit PCM).
    
    Args:
        audio_file_path: Path to the input audio file (MP3 or M4A)
        output_path: Optional path for output WAV file. If None, creates a temp file.
    
    Returns:
        Path to the converted WAV file
    """
    path_lower = audio_file_path.lower()
    if path_lower.endswith(".mp3"):
        audio = AudioSegment.from_mp3(audio_file_path)
    elif path_lower.endswith(".m4a"):
        audio = AudioSegment.from_file(audio_file_path, format="m4a")
    else:
        raise ValueError(f"Unsupported format for conversion: {audio_file_path}")
    
    # Convert to mono, 16kHz, 16-bit PCM (required by Vosk)
    audio = audio.set_channels(1)  # Mono
    audio = audio.set_frame_rate(16000)  # 16kHz sample rate
    audio = audio.set_sample_width(2)  # 16-bit (2 bytes)
    
    if output_path is None:
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
        output_path = temp_file.name
        temp_file.close()
    
    audio.export(output_path, format="wav")
    return output_path


def recognize_from_file(audio_file_path: str) -> str:
    """
    Recognize speech from an audio file (MP3, M4A, or WAV).
    
    Args:
        audio_file_path: Path to the audio file (MP3, M4A, or WAV)
    
    Returns:
        Transcribed text string
    """
    if not os.path.exists(model_path):
        raise FileNotFoundError("Vosk model not found at: " + model_path)
    
    # Convert MP3 or M4A to WAV if needed
    wav_path = audio_file_path
    temp_file_created = False
    path_lower = audio_file_path.lower()
    
    if path_lower.endswith(".mp3") or path_lower.endswith(".m4a"):
        wav_path = _convert_to_wav(audio_file_path)
        temp_file_created = True
    
    try:
        model = Model(model_path)
        recognizer = KaldiRecognizer(model, 16000)
        recognizer.SetWords(True)
        
        wf = wave.open(wav_path, "rb")
        
        # Check if audio format is correct
        if wf.getnchannels() != 1:
            raise ValueError("Audio file must be mono")
        if wf.getsampwidth() != 2:
            raise ValueError("Audio file must be 16-bit")
        if wf.getcomptype() != "NONE":
            raise ValueError("Audio file must be uncompressed")
        
        text_parts = []
        
        # Process audio in chunks
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            
            if recognizer.AcceptWaveform(data):
                result = json.loads(recognizer.Result())
                text = result.get("text", "")
                if text:
                    text_parts.append(text)
        
        # Get final result
        final_result = json.loads(recognizer.FinalResult())
        final_text = final_result.get("text", "")
        if final_text:
            text_parts.append(final_text)
        
        wf.close()
        
        # Combine all text parts
        full_text = " ".join(text_parts).strip()
        return full_text if full_text else ""
    
    finally:
        # Clean up temporary file if we created one
        if temp_file_created and os.path.exists(wav_path):
            os.unlink(wav_path)
