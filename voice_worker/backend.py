"""The voice agent's line to the painting assistant: every thing the caller says goes to POST /incoming as a text
message from that customer, and the assistant's reply comes back as text to be spoken. The assistant's own rules
(screening, grounding, price handling) therefore apply to calls exactly as they do to chat.

Standard library only, so it can be tested without LiveKit installed.
"""
import asyncio
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid

MAX_SPOKEN_CHARS = 1000



# Words the speech model should favour; callers have accents and phone lines are noisy. Extend with VOICE_STT_KEYTERMS.
KEYTERMS = ["sitting room", "living room", "master bedroom", "bedroom", "bathroom", "kitchen", "dining room",
            "ceiling", "skirting", "wall", "walls", "repaint", "meters", "feet", "Jotun", "Nippon Paint", "Dulux",
            "economy", "standard", "premium", "ruang tamu", "bilik tidur", "dinding", "siling", "cat", "kali"]


def keyterms():
    extra = [w.strip() for w in os.environ.get("VOICE_STT_KEYTERMS", "").split(",") if w.strip()]
    return KEYTERMS + extra


_HYPE = re.compile(r"(?:(?<=[.?!])|^)\s*(?:perfect|great|wonderful|awesome|fantastic|excellent|brilliant|lovely|"
                   r"sure thing|of course|absolutely|bagus|hebat)\s*[.!,]+\s*(?=\S)", re.I)


def spoken(replies):
    """Reply text as it should be said aloud: calm, no bullets, labels, symbols or line breaks, never "dot" or
    "slash", and not a wall of speech."""
    text = " ".join(r for r in replies if r)
    text = re.sub(r"https?://\S+", "", text)                    # a link cannot be said
    text = re.sub(r"\(\s*demo\s*\)", "", text, flags=re.I)
    text = re.sub(r"^\s*[-*]\s*", "", text, flags=re.M)         # list bullets
    text = re.sub(r"\s*\n\s*", ". ", text)                      # one line per sentence
    text = re.sub(r"\.{2,}|\u2026", ",", text)                  # "..." is read as "dot dot dot"
    text = text.replace("!", ".")                               # a calm voice, not an excited one
    for _ in range(3):
        text = _HYPE.sub(" ", text)                             # "Perfect." and "Great." in front of every question
    text = re.sub(r"(\d)\.0\b", r"\1", text)                    # "4.0 meters" is "4 meters"
    text = re.sub(r"(\d)\.(\d)", r"\1 point \2", text)          # "3.5" is "3 point 5", not "3 dot 5"
    text = re.sub(r"\b(Sdn|Bhd|No|St|Rd|Jln|Mr|Mrs|Ms|Dr)\.", r"\1", text)      # abbreviation dots
    text = re.sub(r"(?<=\w)\.(?=\w)", " ", text)                # "e.g." or "a.m." or a stray dot inside a word
    text = re.sub(r"\b(\d+(?:\s?point\s?\d+)?)\s?m\b", r"\1 meters", text)     # "4 m long" is "4 meters long"
    text = re.sub(r"\s*[/\\|]\s*", ", ", text)                  # a slash is read aloud
    text = re.sub(r"\s+\.", ".", text)
    text = re.sub(r"\.\s*\.", ".", text)
    text = re.sub(r",\s*,", ",", text)
    text = re.sub(r"[*_`#~<>\[\]{}]+", "", text)
    text = re.sub(r"\bmetres\b", "meters", text)                # "meters" is how the voice says it
    text = re.sub(r"\bmetre\b", "meter", text)
    text = re.sub(r"\bMetres\b", "Meters", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > MAX_SPOKEN_CHARS:
        cut = text[:MAX_SPOKEN_CHARS]
        end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
        text = cut[: end + 1].strip() if end > 0 else cut
    return text


class Backend:
    def __init__(self, base_url, api_key, user_id, call_id, timeout=150):
        self.url = base_url.rstrip("/") + "/incoming"
        self.api_key, self.user_id, self.call_id, self.timeout = api_key, user_id, call_id, timeout
        self.turn = 0
        self.lang = "en"
        self.end_call = False           # the assistant says the conversation is over: say goodbye and hang up

    def _ask(self, text):
        self.turn += 1
        body = {"message_id": f"{self.call_id}:{self.turn}:{uuid.uuid4().hex[:8]}", "user_id": self.user_id,
                "type": "text", "text": text, "channel": "voice"}
        request = urllib.request.Request(self.url, data=json.dumps(body).encode(), method="POST",
                                         headers={"content-type": "application/json", "x-api-key": self.api_key})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.load(response)
        except urllib.error.HTTPError as err:
            raise RuntimeError(f"the assistant answered HTTP {err.code}") from err
        except (OSError, ValueError) as err:
            raise RuntimeError(f"the assistant could not be reached: {err}") from err
        self.lang = data.get("lang") or self.lang
        self.end_call = bool(data.get("end_call"))
        return spoken(data.get("replies") or [])

    def _persona(self):
        """The character the dashboard has switched on: {name, voice, ...}, or {} if it cannot be read."""
        base = self.url.rsplit("/incoming", 1)[0]
        request = urllib.request.Request(base + "/api/personas", headers={"x-api-key": self.api_key})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                data = json.load(response)
        except (OSError, ValueError):               # no network, a timeout, or a reply that is not JSON
            return {}
        return (data.get("personas") or {}).get(data.get("active")) or {}

    def _pending(self, end=False):
        """What the assistant has to tell the caller about things sent in the chat during the call."""
        base = self.url.rsplit("/incoming", 1)[0]
        query = f"?user_id={urllib.parse.quote(self.user_id)}" + ("&end=true" if end else "")
        request = urllib.request.Request(base + "/api/voice/pending" + query, headers={"x-api-key": self.api_key})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                data = json.load(response)
        except (OSError, ValueError):
            return []
        self.lang = data.get("lang") or self.lang
        return [s for s in (spoken([t]) for t in data.get("say") or []) if s]

    async def pending(self, end=False):
        return await asyncio.to_thread(self._pending, end)

    async def persona(self):
        return await asyncio.to_thread(self._persona)

    async def ask(self, text):
        """The words to say for what the caller said ("" when the assistant chose to stay quiet)."""
        return await asyncio.to_thread(self._ask, text)
