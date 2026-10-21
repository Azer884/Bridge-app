

"""
Interactive Live Voice Call Runner for Orbyte Quote Agent
Allows you to speak into your microphone and hear the voice bot reply aloud!

Usage:
  python live_call.py
"""

import sys
import time
import requests
from pathlib import Path
import sounddevice as sd
import soundfile as sf
import numpy as np

PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR))

from voice_loop import VoiceLoop

RECORDINGS_DIR = PROJECT_DIR / "data" / "recordings"
RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

def record_microphone(duration_sec: int = 5, sample_rate: int = 16000) -> Path:
    """Record audio from microphone for specified duration and save as WAV."""
    print(f"\n[Microphone] 🎤 Recording for {duration_sec} seconds... Speak now!")
    audio = sd.rec(int(duration_sec * sample_rate), samplerate=sample_rate, channels=1, dtype='float32')
    sd.wait()
    print("[Microphone] Finished recording.")

    filename = RECORDINGS_DIR / f"mic_{int(time.time())}.wav"
    sf.write(str(filename), audio, sample_rate)
    return filename

def main():
    print("=" * 70)
    print("        ORBYTE QUOTE AGENT - LIVE MICROPHONE CALL RUNNER        ")
    print("=" * 70)

    # Check chatbot server
    try:
        r = requests.get("http://127.0.0.1:8000/health", timeout=1)
        if r.status_code != 200:
            raise Exception()
    except Exception:
        print("[Warning] Chatbot stub server not detected at http://127.0.0.1:8000.")
        print("Please run in a separate terminal: python chatbot_stub.py")
        print("Starting local chatbot server in background now for convenience...")
        import subprocess
        subprocess.Popen([sys.executable, str(PROJECT_DIR / "chatbot_stub.py")])
        time.sleep(2)

    conversation_id = f"call_{int(time.time())}"
    voice_agent = VoiceLoop(conversation_id=conversation_id)

    print("\n[Controls]:")
    print("  - Press [Enter] to record 5 seconds from your microphone")
    print("  - Type 'extract' or 'done' or 'exit' to end call and get JSON")
    print("=" * 70)

    while True:
        try:
            cmd = input("\nPress [Enter] to speak (or type 'exit' / 'done'): ").strip().lower()
            if cmd in ["exit", "quit", "done", "extract", "bye", "selesai"]:
                break

            audio_file = record_microphone(duration_sec=5)
            voice_agent.process_turn(audio_file, play_audio=True)

        except KeyboardInterrupt:
            print("\nCall interrupted.")
            break

    # End call and trigger extraction
    voice_agent.end_call_and_extract()
    print("\nCall complete. Transcript saved in data/transcripts/")

if __name__ == "__main__":
    main()
