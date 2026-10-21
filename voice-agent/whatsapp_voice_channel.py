"""
WhatsApp Voice Channel Handler for Orbyte Quote Agent
Handles:
1. Inbound WhatsApp voice notes (.ogg / .opus / .mp3)
2. STT transcription via faster-whisper
3. Dialog turn via Chatbot POST /chat
4. TTS synthesis and FFmpeg conversion into WhatsApp-compatible Opus voice notes
5. Automatic transcript logging and end-of-call /extract triggering for teammates' price calculator.
"""

import os
import shutil
import subprocess
import requests
import json
from pathlib import Path
from typing import Dict, Any, Optional

from stt_service import STTService
from tts_service import TTSService
from transcript_manager import TranscriptManager

DATA_DIR = Path(__file__).resolve().parent / "data" / "whatsapp_media"
DATA_DIR.mkdir(parents=True, exist_ok=True)

def find_ffmpeg_binary() -> str:
    which_ffmpeg = shutil.which("ffmpeg")
    if which_ffmpeg:
        return which_ffmpeg
    # Common Windows winget path
    winget_default = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    for candidate in winget_default.glob("**/ffmpeg.exe"):
        if candidate.is_file():
            return str(candidate)
    return "ffmpeg"

FFMPEG_BIN = find_ffmpeg_binary()

class WhatsAppVoiceChannel:
    def __init__(self, chatbot_url: str = "http://127.0.0.1:8000"):
        self.chatbot_url = chatbot_url
        self.stt = STTService(model_size="base", device="cpu")
        self.tts = TTSService()
        self.transcript_manager = TranscriptManager()

    def convert_to_whatsapp_opus(self, input_audio_path: Path, output_opus_path: Path) -> Path:
        """
        Convert any audio into WhatsApp-compliant OGG Opus voice note:
        codec: libopus, sample_rate: 16000, channels: 1
        """
        output_opus_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            FFMPEG_BIN, "-y",
            "-i", str(input_audio_path),
            "-c:a", "libopus",
            "-b:a", "24k",
            "-ar", "16000",
            "-ac", "1",
            str(output_opus_path)
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg conversion failed: {res.stderr}")
        return output_opus_path

    def handle_incoming_voice_note(
        self,
        sender_phone_or_id: str,
        audio_file_path: Path
    ) -> Dict[str, Any]:
        """
        Process an incoming WhatsApp voice note from a customer:
        1. Transcribe audio with faster-whisper
        2. Record turn in transcript
        3. Query chatbot POST /chat
        4. Synthesize reply text with edge-tts
        5. Convert reply audio to WhatsApp .ogg (opus) format
        """
        conversation_id = f"wa_{sender_phone_or_id}"
        print(f"\n[WhatsApp Channel: {conversation_id}] Processing voice note from {sender_phone_or_id}...")

        # 1. Transcribe incoming voice note
        stt_result = self.stt.transcribe(str(audio_file_path))
        transcribed_text = stt_result["text"]
        lang = stt_result["language"]
        print(f" -> Transcribed ({lang}): \"{transcribed_text}\"")

        # 2. Record customer turn
        self.transcript_manager.record_turn(
            conversation_id=conversation_id,
            speaker="customer",
            text=transcribed_text
        )

        # 3. Call chatbot POST /chat
        try:
            resp = requests.post(
                f"{self.chatbot_url}/chat",
                json={"conversation_id": conversation_id, "text": transcribed_text},
                timeout=10
            )
            resp.raise_for_status()
            reply_text = resp.json().get("reply", "")
        except Exception as e:
            reply_text = f"Maaf, pelayan sebut harga sedang sibuk. (Error: {e})"

        print(f" -> Chatbot Reply: \"{reply_text}\"")

        # 4. Record agent turn
        self.transcript_manager.record_turn(
            conversation_id=conversation_id,
            speaker="agent",
            text=reply_text
        )

        # 5. Synthesize reply TTS MP3
        temp_mp3 = self.tts.synthesize(reply_text, f"reply_{conversation_id}.mp3")

        # 6. Convert to WhatsApp Voice Note (.ogg with opus)
        out_ogg = DATA_DIR / f"reply_{conversation_id}.ogg"
        self.convert_to_whatsapp_opus(temp_mp3, out_ogg)
        print(f" -> WhatsApp Voice Note generated: {out_ogg} (size: {out_ogg.stat().st_size} bytes)")

        return {
            "conversation_id": conversation_id,
            "sender": sender_phone_or_id,
            "incoming_text": transcribed_text,
            "detected_language": lang,
            "reply_text": reply_text,
            "reply_voice_note_path": str(out_ogg)
        }

    def trigger_extract(self, sender_phone_or_id: str) -> Dict[str, Any]:
        """Trigger /extract when enquiry concludes to pass JSON to price calculator."""
        conversation_id = f"wa_{sender_phone_or_id}"
        transcript = self.transcript_manager.export_for_extract(conversation_id)
        resp = requests.post(
            f"{self.chatbot_url}/extract",
            json={"conversation_id": conversation_id, "transcript": transcript},
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()

if __name__ == "__main__":
    print("WhatsApp Voice Channel module loaded successfully.")
