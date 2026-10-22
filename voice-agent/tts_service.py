"""
Text-to-Speech Service — ElevenLabs only.
Voices:
  Female English : YEENOUza6MPsbkc1De9E
  Female Malay   : BeIxObt4dYBRJLYoe1hU
  Male   English : Q0Et7LOU7VpeoeCRQAVS
  Male   Malay   : 4tIOhnhjaEJdOZjaiV4G
"""

import os
import re
import requests
from pathlib import Path
from typing import Optional

AUDIO_CACHE_DIR = Path(__file__).resolve().parent / "data" / "audio_cache"
AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Load .env if present
_ENV_FILE = Path(__file__).resolve().parent / ".env"
if _ENV_FILE.exists():
    with open(_ENV_FILE, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())


class TTSService:
    ELEVENLABS_VOICES = {
        "female": {"en": "YEENOUza6MPsbkc1De9E", "ms": "BeIxObt4dYBRJLYoe1hU"},
        "male":   {"en": "Q0Et7LOU7VpeoeCRQAVS", "ms": "4tIOhnhjaEJdOZjaiV4G"},
    }

    def __init__(self, gender: str = "female"):
        self.gender = gender.lower()
        self.eleven_api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()

    def detect_language(self, text: str) -> str:
        malay_keywords = [
            "saya", "awak", "kami", "anda", "nak", "cat", "bilik", "dinding",
            "rumah", "kaki", "meter", "kupas", "retak", "warna", "bila",
            "sabtu", "ahad", "pagi", "petang", "terima", "kasih", "sebut", "harga",
        ]
        text_lower = text.lower()
        hits = sum(1 for kw in malay_keywords if re.search(r'\b' + kw + r'\b', text_lower))
        return "ms" if hits >= 2 else "en"

    def get_voice_id(self, text: str, lang: Optional[str] = None) -> str:
        chosen_lang = lang or self.detect_language(text)
        gender_map = self.ELEVENLABS_VOICES.get(self.gender, self.ELEVENLABS_VOICES["female"])
        return gender_map.get(chosen_lang, gender_map["en"])

    def synthesize(
        self,
        text: str,
        output_filename: Optional[str] = None,
        lang: Optional[str] = None,
        voice_id: Optional[str] = None,
    ) -> Path:
        """Synthesize text to .mp3 via ElevenLabs. Raises RuntimeError if API key missing."""
        if not self.eleven_api_key:
            raise RuntimeError(
                "ELEVENLABS_API_KEY not set. Create a .env file with:\n"
                "  ELEVENLABS_API_KEY=your_key_here"
            )

        if output_filename:
            out_path = AUDIO_CACHE_DIR / output_filename
        else:
            safe = re.sub(r'[^a-zA-Z0-9]', '_', text[:20])
            out_path = AUDIO_CACHE_DIR / f"tts_{safe}_{abs(hash(text)) % 100000}.mp3"

        vid = voice_id or self.get_voice_id(text, lang)
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{vid}"
        headers = {
            "xi-api-key": self.eleven_api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8},
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=20)
        if resp.status_code != 200:
            raise RuntimeError(f"ElevenLabs API error {resp.status_code}: {resp.text[:200]}")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as fh:
            fh.write(resp.content)
        return out_path

    def play_audio(self, audio_path: Path):
        """Play audio through default speakers."""
        import soundfile as sf
        import sounddevice as sd
        data, fs = sf.read(str(audio_path), dtype="float32")
        sd.play(data, fs)
        sd.wait()


if __name__ == "__main__":
    tts = TTSService(gender="female")
    ms_text = "Helo! Saya pembantu sebut harga cat dinding. Boleh beritahu saiz bilik anda?"
    out = tts.synthesize(ms_text, "test_malay.mp3")
    print(f"Malay → {out} ({out.stat().st_size} bytes)")

    en_text = "Got it, 4 by 5 metres. How is the condition of your walls?"
    out_en = tts.synthesize(en_text, "test_english.mp3")
    print(f"English → {out_en} ({out_en.stat().st_size} bytes)")
