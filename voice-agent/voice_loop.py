"""
Voice Loop Pipeline for Orbyte Quote Agent
Implements:
  Customer speaks -> STT -> text -> chatbot -> reply text -> TTS -> customer hears it
                          |
             transcript saved per conversation_id
                          |
        end of call -> /extract -> job details JSON -> (price calculator)

Rules strictly enforced:
- Bot never quotes price
- Bot never confirms day/time (reads back preference, owner will confirm)
- Bot confirms dimensions from customer
- Sentences are short and voice-tailored in English / Malay
"""

import time
import uuid
import requests
import json
from pathlib import Path
from typing import Optional, Dict, Any, List

from stt_service import STTService
from tts_service import TTSService
from transcript_manager import TranscriptManager

CHATBOT_URL = "http://127.0.0.1:8000"

class VoiceLoop:
    def __init__(
        self,
        conversation_id: Optional[str] = None,
        chatbot_base_url: str = CHATBOT_URL,
        device: str = "cpu",
        model_size: str = "base"
    ):
        self.conversation_id = conversation_id or f"conv_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        self.chatbot_url = chatbot_base_url
        self.transcript_manager = TranscriptManager()
        self.stt = STTService(model_size=model_size, device=device)
        self.tts = TTSService()
        self.audio_cache = Path(__file__).resolve().parent / "data" / "voice_loop_audio"
        self.audio_cache.mkdir(parents=True, exist_ok=True)

    def process_turn(self, audio_file_path: Path, play_audio: bool = False) -> Dict[str, Any]:
        """
        Process a single spoken customer turn from an audio file:
        1. STT: transcribe audio to text
        2. Save customer turn to transcript
        3. Send text to Chatbot POST /chat
        4. Save agent reply to transcript
        5. TTS: synthesize reply audio
        6. Optionally play audio
        """
        print(f"\n[Voice Loop: {self.conversation_id}] Processing turn...")

        # 1. Speech-to-text
        t0 = time.time()
        stt_result = self.stt.transcribe(str(audio_file_path))
        customer_text = stt_result["text"]
        detected_lang = stt_result["language"]
        stt_time = round(time.time() - t0, 3)
        print(f" -> Customer Spoke ({detected_lang}, {stt_time}s): \"{customer_text}\"")

        # 2. Save customer turn
        self.transcript_manager.record_turn(
            conversation_id=self.conversation_id,
            speaker="customer",
            text=customer_text
        )

        # 3. Call Chatbot POST /chat
        try:
            resp = requests.post(
                f"{self.chatbot_url}/chat",
                json={"conversation_id": self.conversation_id, "text": customer_text},
                timeout=10
            )
            resp.raise_for_status()
            reply_text = resp.json().get("reply", "")
        except Exception as e:
            reply_text = f"Maaf, saya tidak dapat berhubung dengan pelayan. Sila cuba lagi. (Error: {e})"

        print(f" -> Agent Reply: \"{reply_text}\"")

        # 4. Save agent turn
        self.transcript_manager.record_turn(
            conversation_id=self.conversation_id,
            speaker="agent",
            text=reply_text
        )

        # 5. Synthesize TTS reply
        turn_id = int(time.time() * 1000) % 1000000
        reply_audio_path = self.tts.synthesize(
            text=reply_text,
            output_filename=f"reply_{self.conversation_id}_{turn_id}.mp3"
        )
        print(f" -> TTS Generated: {reply_audio_path.name}")

        # 6. Play audio if requested
        if play_audio:
            try:
                self.tts.play_audio(reply_audio_path)
            except Exception as e:
                print(f"    (Audio playback note: {e})")

        return {
            "customer_text": customer_text,
            "detected_language": detected_lang,
            "agent_reply": reply_text,
            "reply_audio_path": str(reply_audio_path)
        }

    def end_call_and_extract(self) -> Dict[str, Any]:
        """
        Finalize conversation: sends full transcript to POST /extract
        and retrieves structured job details for teammates' price calculator.
        """
        print(f"\n[Voice Loop: {self.conversation_id}] Ending call and extracting job details...")
        formatted_transcript = self.transcript_manager.export_for_extract(self.conversation_id)

        try:
            resp = requests.post(
                f"{self.chatbot_url}/extract",
                json={"conversation_id": self.conversation_id, "transcript": formatted_transcript},
                timeout=10
            )
            resp.raise_for_status()
            extract_data = resp.json()
        except Exception as e:
            extract_data = {"error": f"Failed to call /extract: {e}"}

        print("=" * 60)
        print(f"   EXTRACTED JOB DETAILS (Ready for Price Calculator)   ")
        print("=" * 60)
        print(json.dumps(extract_data, indent=2, ensure_ascii=False))
        print("=" * 60)
        return extract_data

    def simulate_full_call(self, customer_turns: List[str]):
        """Simulate an entire customer voice call from a list of spoken statements."""
        print("=" * 70)
        print(f" STARTING SIMULATED VOICE CALL: {self.conversation_id} ")
        print("=" * 70)

        for i, turn_text in enumerate(customer_turns, 1):
            print(f"\n[Turn {i}/{len(customer_turns)}]")
            # Generate speech for customer input
            audio_in = self.tts.synthesize(turn_text, f"sim_customer_turn_{i}.mp3")
            # Run through voice pipeline
            self.process_turn(audio_in, play_audio=False)

        # End of call -> trigger /extract
        extracted = self.end_call_and_extract()
        return extracted

if __name__ == "__main__":
    import sys
    print("Voice Loop Engine ready. Run simulated call or test via runner.")
