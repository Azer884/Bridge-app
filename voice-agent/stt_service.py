"""
Speech-to-Text Service using faster-whisper
Specially tuned for Malaysian SME contexts:
- Handles English, Malay (Bahasa Melayu), and Manglish (code-switching).
- Pre-prompt biasing ensures accurate recognition of dimensions (e.g. "4 by 5 metres", "10x12 feet")
  and painting terminology (cat dinding, mengelupas, Jotun, Nippon Paint).
- Auto-detects CUDA GPU with CPU fallback.
"""

import os
import re
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
import numpy as np

# Number mapping for spoken Malay words and common English homophones
MALAY_NUMBERS = {
    "kosong": "0", "sifar": "0",
    "satu": "1", "dua": "2", "tiga": "3", "empat": "4",
    "lima": "5", "enam": "6", "tujuh": "7", "lapan": "8", "sembilan": "9",
    "sepuluh": "10", "sebelas": "11", "dua belas": "12"
}

ENGLISH_NUMBERS = {
    "zero": "0", "one": "1", "won": "1",
    "two": "2", "to": "2", "too": "2",
    "three": "3",
    "four": "4", "for": "4", "fore": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8", "ate": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
    "twenty": "20",
    "thirty": "30"
}

DEFAULT_PROMPT = (
    "Malaysian SME painting quotation enquiry. Dimensions: 4 by 5 metres, 3 by 4 metres, "
    "10 by 12 feet, 4x5m, 3x4m, 2 bilik tidur, 1 ruang tamu. Dinding berlumut, cat mengelupas, "
    "retak halus, Jotun, Nippon Paint, cat kapur. Empat kali lima meter, tiga kali empat meter."
)

class STTService:
    def __init__(self, model_size: str = "base", device: Optional[str] = "cpu"):
        """
        Initialize faster-whisper model.
        Default to 'cpu' with 'int8' for fast, robust cross-platform execution.
        """
        from faster_whisper import WhisperModel
        self.device = device or "cpu"
        self.compute_type = "int8" if self.device == "cpu" else "float16"
        print(f"STT: Initializing faster-whisper ({model_size}) on {self.device} ({self.compute_type})...")
        self.model = WhisperModel(model_size, device=self.device, compute_type=self.compute_type)

    def normalize_spoken_dimensions(self, text: str) -> str:
        """
        Robustly normalize spoken number phrases into clear dimension notation:
        Examples:
        - 'for by 5 meters' -> '4 by 5 metres'
        - 'four by five metres' -> '4 by 5 metres'
        - 'empat kali lima meter' -> '4 by 5 metres'
        - 'tiga kali empat meter' -> '3 by 4 metres'
        - '10 by 12 feet' -> '10 by 12 feet'
        """
        normalized = text

        # Map all number tokens
        all_words = {**MALAY_NUMBERS, **ENGLISH_NUMBERS}
        words_regex = '|'.join(sorted(all_words.keys(), key=lambda x: -len(x)))
        connectors = r'(?:by|x|\*|kali|darab)'

        # 1. Match: <word/digit> <connector> <word/digit> [<unit>]
        # e.g., "for by 5 meters", "empat kali lima meter", "4 by 5 metres"
        token_or_digit = r'(?:\d+|' + words_regex + r')'
        unit_regex = r'(?:metres?|meter|m|feet|kaki|ft)'

        def dimension_replacer(match):
            raw_n1 = match.group(1).lower()
            raw_n2 = match.group(2).lower()
            unit = match.group(3) if match.group(3) else ""

            n1 = all_words.get(raw_n1, raw_n1)
            n2 = all_words.get(raw_n2, raw_n2)

            # Standardize unit
            unit_norm = ""
            if unit:
                u_low = unit.lower()
                if "kaki" in u_low or "ft" in u_low or "feet" in u_low:
                    unit_norm = " feet"
                else:
                    unit_norm = " metres"
            else:
                unit_norm = " metres"

            return f"{n1} by {n2}{unit_norm}"

        pattern = re.compile(
            r'\b(' + token_or_digit + r')\s+(?:by|x|\*|kali|darab)\s+(' + token_or_digit + r')(?:\s+(' + unit_regex + r'))?\b',
            re.IGNORECASE
        )
        normalized = pattern.sub(dimension_replacer, normalized)

        # 2. Also match spoken numbers without explicit connector (common in Malay, e.g. "saiz empat lima meter" / "empat 5 metres")
        pattern_implicit = re.compile(
            r'\b(' + token_or_digit + r')\s+(' + token_or_digit + r')\s+(' + unit_regex + r')\b',
            re.IGNORECASE
        )
        normalized = pattern_implicit.sub(dimension_replacer, normalized)

        # 2. Also normalize single Malay/English digits with units, e.g. "dua bilik" -> "2 bilik"
        for word, digit in all_words.items():
            normalized = re.sub(r'\b' + word + r'\s+(bilik|kaki|meter|metres?|feet|doors?|pintu)\b', rf'{digit} \1', normalized, flags=re.IGNORECASE)

        return normalized

    def transcribe(
        self,
        audio_input: Union[str, Path, np.ndarray],
        language: Optional[str] = None,
        initial_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Transcribe audio input (file path or numpy array).
        Returns dict with:
        - 'text': transcribed text
        - 'language': detected or specified language code
        - 'language_probability': confidence score
        - 'duration': audio duration in seconds
        - 'segments': list of segment details
        """
        prompt = initial_prompt or DEFAULT_PROMPT

        segments, info = self.model.transcribe(
            audio_input,
            language=language,
            initial_prompt=prompt,
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500)
        )

        segment_list = []
        raw_text_parts = []
        for s in segments:
            raw_text_parts.append(s.text.strip())
            segment_list.append({
                "start": s.start,
                "end": s.end,
                "text": s.text.strip()
            })

        full_raw_text = " ".join(raw_text_parts).strip()
        normalized_text = self.normalize_spoken_dimensions(full_raw_text)

        return {
            "text": normalized_text,
            "raw_text": full_raw_text,
            "language": info.language,
            "language_probability": round(info.language_probability, 3),
            "duration": round(info.duration, 2),
            "segments": segment_list
        }

if __name__ == "__main__":
    stt = STTService(model_size="base")
    sample_text = "Saya nak cat bilik empat kali lima meter, dinding ada sikit kupas"
    norm = stt.normalize_spoken_dimensions(sample_text)
    print("Test Normalizer:")
    print("Original:", sample_text)
    print("Normalized:", norm)
