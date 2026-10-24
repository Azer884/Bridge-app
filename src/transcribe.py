"""Voice notes -> text. Uses faster-whisper, tuned for Malaysian customers (English, Malay, Manglish) like the
team's voice-agent branch: a biasing prompt for painting words and a normaliser for spoken sizes
("empat kali lima meter" -> "4 by 5 metres"). The text then goes through the same screening, grounding and
validation as a typed message.

The model loads on first use, in the server process: `faster-whisper` must be installed
(`uv add faster-whisper` on Replit). Without it voice notes are answered with a polite "please type it".
"""
import logging
import os
import re
import tempfile
import threading
from pathlib import Path

log = logging.getLogger("transcribe")

MALAY_NUMBERS = {"kosong": "0", "sifar": "0", "satu": "1", "dua": "2", "tiga": "3", "empat": "4", "lima": "5",
                 "enam": "6", "tujuh": "7", "lapan": "8", "sembilan": "9", "sepuluh": "10", "sebelas": "11"}
ENGLISH_NUMBERS = {"zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
                   "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12"}
# speech-to-text often writes these instead of the number, but only inside "<n> by <n>"
HOMOPHONES = {"won": "1", "to": "2", "too": "2", "for": "4", "fore": "4", "ate": "8"}

DEFAULT_PROMPT = (
    "Malaysian painting quotation enquiry. Dimensions: 4 by 5 metres, 3 by 4 metres, 10 by 12 feet, 4x5m. "
    "Cat dinding, siling, bilik tidur, ruang tamu, cat mengelupas, retak, lembap, berkulat, Jotun, Nippon Paint. "
    "Empat kali lima meter, tiga kali empat meter."
)

_WORDS = {**MALAY_NUMBERS, **ENGLISH_NUMBERS}
_NUMBER = r"\d+(?:\.\d+)?|" + "|".join(sorted(map(re.escape, {**_WORDS, **HOMOPHONES}), key=len, reverse=True))
_UNIT = r"metres?|meters?|meter|m|feet|kaki|ft"
_PAIR = re.compile(rf"\b({_NUMBER})\s+(?:by|x|\*|kali|darab)\s+({_NUMBER})(?:\s+({_UNIT}))?\b", re.I)
_SINGLE = re.compile(rf"\b({'|'.join(sorted(map(re.escape, _WORDS), key=len, reverse=True))})\s+({_UNIT})\b", re.I)


def _digit(token):
    token = token.lower()
    return {**_WORDS, **HOMOPHONES}.get(token, token)


def normalize_spoken(text):
    """Spoken sizes become written ones, so the grounding checks can read them."""
    def pair(match):
        unit = (match.group(3) or "metres").lower()
        unit = "feet" if unit in ("kaki", "ft", "feet") else "metres"
        return f"{_digit(match.group(1))} by {_digit(match.group(2))} {unit}"

    def single(match):
        return f"{_digit(match.group(1))} {match.group(2)}"

    return _SINGLE.sub(single, _PAIR.sub(pair, text))


class Transcriber:
    def __init__(self, model_size="base", device="cpu", model_factory=None):
        self.model_size, self.device = model_size, device
        self._factory, self._model, self._lock = model_factory, None, threading.Lock()

    @classmethod
    def from_env(cls, env):
        """None when voice is switched off (STT_ENABLED=0). The model itself loads on first use."""
        if str(env.get("STT_ENABLED", "1")).lower() in ("0", "false", "no", "off"):
            return None
        return cls(env.get("STT_MODEL_SIZE") or "base", env.get("STT_DEVICE") or "cpu")

    def _load(self):
        with self._lock:
            if self._model is None:
                if self._factory:
                    self._model = self._factory()
                else:
                    from faster_whisper import WhisperModel           # optional dependency
                    compute = "int8" if self.device == "cpu" else "float16"
                    self._model = WhisperModel(self.model_size, device=self.device, compute_type=compute)
        return self._model

    def transcribe(self, audio, mime=""):
        """(text, detected language) for the audio bytes of a voice note. Raises on any failure."""
        model = self._load()
        suffix = ".ogg" if "ogg" in mime or "opus" in mime or not mime else ".m4a" if "mp4" in mime or "aac" in mime else ".mp3"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
            handle.write(audio)
            path = handle.name
        try:
            segments, info = model.transcribe(path, language=None, initial_prompt=DEFAULT_PROMPT, beam_size=5,
                                              vad_filter=True, vad_parameters={"min_silence_duration_ms": 500})
            text = " ".join(segment.text.strip() for segment in segments).strip()
        finally:
            Path(path).unlink(missing_ok=True)
        return normalize_spoken(text), getattr(info, "language", "")
