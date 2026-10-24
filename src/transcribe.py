"""Voice notes -> text. Uses faster-whisper, tuned for Malaysian customers (English, Malay, Manglish) like the
team's voice-agent branch: a biasing prompt for painting words and a normaliser for spoken sizes
("empat kali lima meter" -> "4 by 5 metres"). The text then goes through the same screening, grounding and
validation as a typed message.

With STT_RUNPOD_ENDPOINT_ID set, the audio goes to a RunPod faster-whisper worker (GPU, much faster than the Replit CPU).
If that call fails, or no endpoint is set, the model loads on first use in the server process: `faster-whisper` must then
be installed (`uv add faster-whisper` on Replit). Without it voice notes are answered with a polite "please type it".
"""
import base64
import importlib.util
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
    "Empat kali lima meter, tiga kali empat meter. Sitting room, living room, master bedroom, kitchen, bathroom, "
    "dining room, ceiling, skirting, repaint, economy, standard, premium."
)
# Phrases speech-to-text writes for a room word when the speaker has an accent or the line is noisy
_MISHEARS = [(re.compile(r"\b(?:sitting|setting|seating)\s+(?:maybe one word|may be one word|rum|rom|rooms?\b)", re.I),
              "sitting room"),
             (re.compile(r"\bliving\s+(?:rum|rom|rube)\b", re.I), "living room"),
             (re.compile(r"\bbed\s+(?:rum|rom)\b", re.I), "bedroom")]

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

    for pattern, fixed in _MISHEARS:
        text = pattern.sub(fixed, text)
    return _SINGLE.sub(single, _PAIR.sub(pair, text))


class Transcriber:
    def __init__(self, model_size="base", device="cpu", model_factory=None, remote=None, remote_model="small"):
        self.model_size, self.device = model_size, device
        self.remote, self.remote_model = remote, remote_model       # a RunPodClient for a faster-whisper worker, or None
        self._factory, self._model, self._lock = model_factory, None, threading.Lock()
        self.last_error = ""                    # why the last load or transcription failed, for /api/voice/health

    @classmethod
    def from_env(cls, env):
        """None when voice is switched off (STT_ENABLED=0). The model itself loads on first use."""
        if str(env.get("STT_ENABLED", "1")).lower() in ("0", "false", "no", "off"):
            return None
        remote = None
        if env.get("STT_RUNPOD_ENDPOINT_ID"):
            from .runpod_client import RunPodClient
            key = env.get("STT_RUNPOD_API_KEY") or env.get("RUNPOD_API_KEY")
            if key:
                remote = RunPodClient(key, env["STT_RUNPOD_ENDPOINT_ID"], timeout_s=180)
        return cls(env.get("STT_MODEL_SIZE") or "base", env.get("STT_DEVICE") or "cpu", remote=remote,
                   remote_model=env.get("STT_RUNPOD_MODEL") or "small")

    @property
    def loaded(self):
        return self._model is not None or self.remote is not None

    def _load(self):
        with self._lock:
            if self._model is None:
                try:
                    if self._factory:
                        self._model = self._factory()
                    else:
                        from faster_whisper import WhisperModel           # optional dependency
                        compute = "int8" if self.device == "cpu" else "float16"
                        self._model = WhisperModel(self.model_size, device=self.device, compute_type=compute)
                    self.last_error = ""
                except Exception as err:
                    self.last_error = f"{type(err).__name__}: {err}"[:300]
                    raise
        return self._model

    @staticmethod
    def decoder_problem():
        """faster-whisper 1.2.1 decodes audio with PyAV, and PyAV 19 removed an argument it passes (every voice note then
        fails with "open() got an unexpected keyword argument 'metadata_errors'"). Returns the fix, or ""."""
        try:
            import av
            if int(av.__version__.split(".")[0]) >= 19:
                return f'PyAV {av.__version__} is too new for faster-whisper: run uv add "av<19"'
        except Exception:
            pass
        return ""

    def warm_up(self):
        """Load the model now (it downloads on first use), so the first voice note is not the slow one.
        With a RunPod worker there is nothing to load here; the local model only loads if the worker fails."""
        if self.remote:
            return True
        if not self._factory and importlib.util.find_spec("faster_whisper") is None:
            self.last_error = "faster-whisper is not installed (uv add faster-whisper)"
            return False
        if not self._factory and self.decoder_problem():
            self.last_error = self.decoder_problem()
            return False
        try:
            self._load()
            return True
        except Exception:
            log.exception("could not load the speech model")
            return False

    def _transcribe_remote(self, audio):
        output = self.remote.run({"audio_base64": base64.b64encode(audio).decode(), "model": self.remote_model,
                                  "language": None, "initial_prompt": DEFAULT_PROMPT, "beam_size": 5})
        text = (output.get("transcription") or " ".join(s.get("text", "").strip() for s in output.get("segments", []))
                ).strip() if isinstance(output, dict) else ""
        if not text:
            raise RuntimeError("RunPod whisper returned no text")
        return normalize_spoken(text), output.get("detected_language", "")

    def transcribe(self, audio, mime=""):
        """(text, detected language) for the audio bytes of a voice note. Raises on any failure."""
        if self.remote:
            try:
                result = self._transcribe_remote(audio)
                self.last_error = ""
                return result
            except Exception as err:
                self.last_error = f"RunPod whisper failed, using local model: {type(err).__name__}: {err}"[:300]
                log.warning(self.last_error)
        model = self._load()
        suffix = ".ogg" if "ogg" in mime or "opus" in mime or not mime else ".m4a" if "mp4" in mime or "aac" in mime else ".mp3"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
            handle.write(audio)
            path = handle.name
        try:
            for vad in (True, False):           # the silence filter can drop a quiet or short note: retry without it
                segments, info = model.transcribe(path, language=None, initial_prompt=DEFAULT_PROMPT, beam_size=5,
                                                  vad_filter=vad, vad_parameters={"min_silence_duration_ms": 500})
                text = " ".join(segment.text.strip() for segment in segments).strip()
                if text:
                    break
        except TypeError as err:
            if "metadata_errors" in str(err):
                self.last_error = self.decoder_problem() or str(err)
                raise RuntimeError(self.last_error) from err
            self.last_error = f"TypeError: {err}"[:300]
            raise
        except Exception as err:
            self.last_error = f"{type(err).__name__}: {err}"[:300]
            raise
        finally:
            Path(path).unlink(missing_ok=True)
        return normalize_spoken(text), getattr(info, "language", "")
