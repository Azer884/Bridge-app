"""
Continuous Hands-Free Voice Call Runner for Orbyte Quote Agent
- Real-time two-way voice conversation like a phone call.
- Bot speaks first to greet customer aloud.
- Auto Voice Activity Detection (VAD): listens when you speak, stops when you are silent.
- No buttons or Enter key needed during the call!
- Plays AI voice reply aloud through speakers.
- Automatically extracts job details at the end of the call.
"""

import sys
import time
import queue
import requests
import subprocess
import numpy as np
import sounddevice as sd
import soundfile as sf
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR))

from voice_loop import VoiceLoop
from tts_service import TTSService

RECORDINGS_DIR = PROJECT_DIR / "data" / "recordings"
RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

import argparse
from typing import Optional

class ContinuousCallRunner:
    def __init__(self, sample_rate: int = 16000, silence_duration: float = 1.3, gender: str = "female", voice: Optional[str] = None):
        self.sample_rate = sample_rate
        self.silence_duration = silence_duration
        self.audio_queue = queue.Queue()
        self.gender = gender.lower()
        self.voice = voice
        self.tts = TTSService(gender=self.gender)
        self.ensure_chatbot_running()
        
        self.conversation_id = f"call_{int(time.time())}"
        self.voice_agent = VoiceLoop(conversation_id=self.conversation_id)

    def ensure_chatbot_running(self):
        try:
            r = requests.get("http://127.0.0.1:8000/health", timeout=1)
            if r.status_code == 200:
                return
        except Exception:
            pass

        print("[Server] Starting Chatbot Stub Server on http://127.0.0.1:8000...")
        subprocess.Popen([sys.executable, str(PROJECT_DIR / "chatbot_stub.py")])
        for _ in range(15):
            time.sleep(0.5)
            try:
                r = requests.get("http://127.0.0.1:8000/health", timeout=1)
                if r.status_code == 200:
                    print("[Server] Server is ready.")
                    return
            except Exception:
                pass
        print("[Warning] Could not confirm server. Proceeding anyway.")

    def calibrate_ambient_noise(self, duration: float = 1.0) -> float:
        """Measure background noise to set speech detection threshold."""
        print("[Mic] Calibrating microphone for background noise... Please stay quiet.")
        samples = []
        def callback(indata, frames, time_info, status):
            samples.append(np.abs(indata.copy()).mean())

        with sd.InputStream(samplerate=self.sample_rate, channels=1, callback=callback):
            sd.sleep(int(duration * 1000))

        ambient_mean = np.mean(samples) if samples else 0.005
        # Set threshold comfortably above ambient noise
        threshold = max(float(ambient_mean * 2.8), 0.015)
        print(f"[Mic] Ready! Ambient level: {ambient_mean:.4f} | Speech Threshold: {threshold:.4f}\n")
        return threshold

    def listen_for_user_speech(self, threshold: float) -> Path:
        """
        Continuously listens until the user speaks and then pauses.
        Returns the path to the recorded WAV audio file.
        """
        print("🎤 [Listening...] Speak anytime! (AI will detect when you stop speaking)")
        
        chunk_queue = queue.Queue()
        def audio_callback(indata, frames, time_info, status):
            chunk_queue.put(indata.copy())

        speech_frames = []
        is_speaking = False
        silence_start_time = None

        with sd.InputStream(samplerate=self.sample_rate, channels=1, callback=audio_callback):
            while True:
                try:
                    data = chunk_queue.get(timeout=0.05)
                except queue.Empty:
                    continue

                amplitude = np.abs(data).mean()

                if not is_speaking:
                    if amplitude > threshold:
                        is_speaking = True
                        print("🗣️  [Voice detected...] Recording your speech...")
                        speech_frames.append(data)
                        silence_start_time = None
                else:
                    speech_frames.append(data)
                    if amplitude < threshold:
                        if silence_start_time is None:
                            silence_start_time = time.time()
                        elif time.time() - silence_start_time >= self.silence_duration:
                            # Finished speaking
                            print("🤫 [Speech paused] Processing turn...")
                            break
                    else:
                        silence_start_time = None

        audio_array = np.concatenate(speech_frames, axis=0)
        output_file = RECORDINGS_DIR / f"turn_{int(time.time()*1000)}.wav"
        sf.write(str(output_file), audio_array, self.sample_rate)
        return output_file

    def bot_speak_aloud(self, text: str):
        """Synthesize text and play it aloud through the speakers."""
        print(f"🤖 Bot ({self.gender}): \"{text}\"")
        audio_path = self.tts.synthesize(
            text,
            f"voice_out_{int(time.time()*1000)}.mp3",
            voice_id=self.voice
        )
        self.tts.play_audio(audio_path)

    def run(self):
        print("=" * 70)
        print("      ORBYTE QUOTE AGENT - CONTINUOUS TWO-WAY VOICE CALL        ")
        print("=" * 70)
        print("Instructions:")
        print(" - The AI will start the call by greeting you aloud.")
        print(" - When it finishes talking, simply reply with your voice.")
        print(" - No typing or key presses needed during the call!")
        print(" - Say 'bye', 'done', 'that's all', or press Ctrl+C to end the call.")
        print("=" * 70)

        threshold = self.calibrate_ambient_noise()

        # Step 1: Initial Bot Greeting Aloud
        initial_greeting = (
            "Hello! I am your painting quotation assistant. "
            "Could you share the dimensions of the room or walls you want painted, for example 4 by 5 metres?"
        )
        self.voice_agent.transcript_manager.record_turn(
            conversation_id=self.conversation_id,
            speaker="agent",
            text=initial_greeting
        )
        self.bot_speak_aloud(initial_greeting)

        # Step 2: Continuous Voice Loop
        turn_count = 0
        max_turns = 10

        while turn_count < max_turns:
            try:
                turn_count += 1
                # 1. Listen for user speech hands-free
                user_audio_file = self.listen_for_user_speech(threshold)

                # 2. Transcribe and check for call exit keywords
                stt_res = self.voice_agent.stt.transcribe(str(user_audio_file))
                spoken_text = stt_res["text"].strip()
                lang = stt_res["language"]
                print(f"👤 You ({lang}): \"{spoken_text}\"")

                # If empty or noise
                if not spoken_text:
                    print("[Mic] No clear speech detected. Listening again...")
                    continue

                # Check if customer wants to end call
                exit_triggers = ["bye", "goodbye", "that's all", "thats all", "done", "selesai", "terima kasih", "thank you that is all"]
                if any(trig in spoken_text.lower() for trig in exit_triggers):
                    farewell = "Thank you! I have recorded all your job details. Our business owner will review the quotation and confirm your appointment. Have a great day!"
                    self.voice_agent.transcript_manager.record_turn(self.conversation_id, "customer", spoken_text)
                    self.voice_agent.transcript_manager.record_turn(self.conversation_id, "agent", farewell)
                    self.bot_speak_aloud(farewell)
                    break

                # 3. Process turn with voice agent
                self.voice_agent.transcript_manager.record_turn(self.conversation_id, "customer", spoken_text)

                resp = requests.post(
                    f"{self.voice_agent.chatbot_url}/chat",
                    json={"conversation_id": self.conversation_id, "text": spoken_text},
                    timeout=10
                )
                resp.raise_for_status()
                reply_text = resp.json().get("reply", "")

                self.voice_agent.transcript_manager.record_turn(self.conversation_id, "agent", reply_text)

                # 4. Speak reply aloud
                self.bot_speak_aloud(reply_text)

            except KeyboardInterrupt:
                print("\n[Call ended by user].")
                break
            except Exception as e:
                print(f"[Error during turn]: {e}")
                break

        # Step 3: End of call -> Trigger /extract
        print("\n" + "=" * 70)
        print("          CALL COMPLETED — EXTRACTING JOB DETAILS JSON           ")
        print("=" * 70)
        extracted = self.voice_agent.end_call_and_extract()
        print(f"\nTranscript saved to: data/transcripts/{self.conversation_id}.json")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Orbyte Continuous Voice Call")
    parser.add_argument(
        "--gender",
        choices=["female", "male", "women", "men"],
        default="female",
        help="Voice gender: female (women) or male (men)"
    )
    parser.add_argument(
        "--voice",
        default=None,
        help="Explicit ElevenLabs Voice ID (optional)"
    )
    args = parser.parse_args()
    chosen_gender = "male" if args.gender in ["male", "men"] else "female"
    runner = ContinuousCallRunner(gender=chosen_gender, voice=args.voice)
    runner.run()
