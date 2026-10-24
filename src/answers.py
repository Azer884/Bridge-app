"""Checks that a stored answer really answers its question, and readers for details a customer volunteers.

The model (and the plain-answer fallback) can put any short reply into the field being asked about: a date into
"surface condition", an address into "condition", "yes that's my number" into the address. These checks keep a value
out of a field it does not belong in; the assistant then asks the question again, in a friendlier way."""
import difflib
import re

from . import flow
from .i18n import COLOUR_WORDS

# words that describe damage: they count in a sentence of any length
CONDITION_STRONG = re.compile(
    r"\b(bad|poor|old|worn|damaged?|peel\w*|flak\w*|crack\w*|damp|moist\w*|wet|leak\w*|mou?ld\w*|mildew|stain\w*|"
    r"bubbl\w*|blister\w*|hole\w*|rough|uneven|dirty|faded|chalk\w*|rust\w*|water ?damage|"
    r"lama|kotor|lembap|kulat|retak|mengelupas|tertanggal|bocor|rosak|kesan)\b", re.I)
# words that only answer the question in a short reply ("good", "ok", "it's fine")
CONDITION_WEAK = re.compile(
    r"\b(good|fine|great|ok(?:ay)?|normal|nice|clean|new|newly|smooth|perfect|excellent|decent|nothing|none|"
    r"no (?:issues?|problems?|damage)|baik|elok|bagus|biasa|baru|tiada)\b", re.I)
STREET = re.compile(
    r"\b(jalan|jln|lorong|lrg|lebuh|persiaran|lengkok|taman|tmn|bandar|kampung|kg|block|blok|unit|lot|level|tingkat|"
    r"apartment|apt|condo|kondo|residensi|residence|villa|street|road|avenue|lane|drive|court|flat|pangsapuri|"
    r"seksyen|section|bukit|presint|precinct|ss\d+|usj)\b|\bno\.?\s*\d", re.I)
COLOUR = re.compile(r"\b(" + "|".join(sorted(COLOUR_WORDS, key=len, reverse=True)) + r"|colou?rs?|warna|shade|pastel|light|dark)\b", re.I)
_COLOUR_CODE = re.compile(r"\b[a-z]*\d{3,}\b", re.I)
_NOT_NAME = {"yes", "no", "ok", "okay", "thanks", "thank", "what", "when", "how", "why", "can", "is", "are", "do",
             "does", "my", "order", "again", "the", "same", "number", "hello", "hi", "sure", "cancel", "stop", "later"}


_CONDITION_FILLER = {"it", "its", "it's", "is", "are", "the", "they", "walls", "wall", "surface", "surfaces", "looks", "look",
                     "so", "quite", "very", "pretty", "still", "really", "all", "and", "la", "lah", "je", "saja", "dia",
                     "keadaan", "semua", "ok", "yes", "yeah", "condition", "overall", "now", "currently", "i", "think",
                     "should", "be", "in", "at", "mostly", "generally", "rather", "kind", "of", "agak", "masih", "nampak"}


def is_condition(message):
    if CONDITION_STRONG.search(message) or flow._BARE_NO.match(message):
        return True
    if not CONDITION_WEAK.search(message) or re.search(r"\d", message):
        return False
    rest = re.findall(r"[a-z']+", CONDITION_WEAK.sub(" ", message.lower()))
    return len(rest) <= 3 and all(w in _CONDITION_FILLER for w in rest)


def is_address(text):
    words = re.findall(r"[A-Za-z0-9]+", text)
    return bool(STREET.search(text) and (re.search(r"\d", text) or len(words) >= 3)) or (
        len(words) >= 4 and "," in text and re.search(r"\d", text) is not None)


def is_colour(message):
    return bool(COLOUR.search(message) or _COLOUR_CODE.search(message) or flow.NO_PREFERENCE.search(message))


def is_name(value):
    words = str(value).split()
    return 1 <= len(words) <= 4 and "?" not in str(value) and not (_NOT_NAME & {w.lower() for w in words}) \
        and all(re.fullmatch(r"[^\W\d_][\w'.\-]*", w) for w in words)


def plausible(key, value, message):
    """False when `value` (taken from `message`) cannot be the answer to `key`."""
    if key == "surface_condition":
        return is_condition(message)
    if key == "preferred_datetime":
        return flow.when_in(message) is not None and not flow._PAST_DATE.search(message)
    if key == "address":
        return is_address(str(value)) or is_address(message)
    if key == "colour":
        return is_colour(message)
    if key == "customer_name":
        return is_name(value)
    return True


# --- details volunteered in any message ----------------------------------------------------------------------------
_ADDRESS_LABEL = re.compile(r"\baddress\s*(?:is|:|-)?\s*(.+)", re.I)
_STREET_NUMBER = re.compile(r"\b(\d+[a-z]?(?:[-/]\d+[a-z]?)?)\s*,?\s+(jalan|jln|lorong|lrg|lebuh|persiaran|lengkok)\b", re.I)
_ADDRESS_STOP = re.compile(
    r"\s*(?:\n|[.;]\s|\b(?:walls?|ceilings?|standard|premium|economy|tomorrow|today|tonight|monday|tuesday|wednesday|"
    r"thursday|friday|saturday|sunday|my name|name:|phone|please|pls|thanks|dinding|siling|esok)\b|\d+\s*[x*]\s*\d)", re.I)
_AREA_START = re.compile(r"\s*,\s*(taman|tmn|bandar|seksyen|section|bukit|kampung|kg|presint|precinct|ss\d|usj)\b", re.I)


def address_in(message):
    """A street address typed inside a longer message ("... at 5 Jalan Mawar, Taman Melati ..."), or None."""
    label = _ADDRESS_LABEL.search(message)
    start = label.start(1) if label else None
    if start is None:
        number = _STREET_NUMBER.search(message)
        start = number.start(1) if number else None
    if start is None:
        return None
    rest = message[start:]
    stop = _ADDRESS_STOP.search(rest)
    rest = rest[:stop.start()] if stop else rest
    pieces = re.split(r"\s*,\s*", rest)
    kept = [pieces[0]]
    for piece in pieces[1:3]:
        if re.search(r"\d{5,}", piece) or not _AREA_START.match("," + piece):
            break
        kept.append(piece)
    text = ", ".join(kept).strip(" ,.-")
    return text[:120] if len(text.split()) >= 2 and is_address(text) else None


_NAME_EXPLICIT = re.compile(
    r"(?:my name is|my name's|name is|name's|name\s*:|nama saya|nama aku|panggil saya|call me)\s*:?\s+"
    r"([^\W\d_][\w'\-]*(?:\s+[^\W\d_][\w'\-]*){0,2})", re.I)


_NAME_INTRO = re.compile(
    r"(?:^|[.!?,]\s*|\bhi\s+|\bhello\s+|\bhai\s+)(?:i'?m|i am|this is|saya)\s+([^\W\d_][\w'\-]*(?:\s+[^\W\d_][\w'\-]*)?)"
    r"(?=\s*(?:$|[.,!]|and\b|dan\b|from\b|my\b|calling\b))", re.I)
_NOT_AN_INTRO = {"looking", "interested", "trying", "planning", "wanting", "thinking", "ready", "just", "not", "here",
                 "new", "sorry", "sure", "happy", "also", "still", "going", "having", "moving", "want", "need", "nak",
                 "mahu", "cari", "ingin", "at", "in", "from", "a", "an", "the"}


def explicit_name(message):
    match = _NAME_EXPLICIT.search(message)
    if not match:
        intro = _NAME_INTRO.search(message)
        if intro and intro.group(1).split()[0].lower() not in _NOT_AN_INTRO:
            match = intro
    if not match:
        return None
    words = match.group(1).split()
    while words and words[-1].lower() in {"and", "phone", "number", "address", "i", "my", "can", "please", "thanks"}:
        words.pop()
    name = " ".join(w.capitalize() if w.islower() else w for w in words)
    return name if name and is_name(name) else None


# --- typing mistakes in the words the backend reads ----------------------------------------------------------------
_VOCAB = ["walls", "wall", "ceiling", "ceilings", "economy", "standard", "premium", "bedroom", "kitchen", "bathroom",
          "dinding", "siling"]
_KEEP = {"calls", "halls", "falls", "ceiling", "walls", "wall", "tall", "will", "well", "bills"}


def fix_typos(message):
    def fix(match):
        word = match.group(0)
        lower = word.lower()
        if lower in _KEEP or lower in _VOCAB:
            return word
        close = difflib.get_close_matches(lower, _VOCAB, n=1, cutoff=0.84)
        return close[0] if close else word
    return re.sub(r"[A-Za-z]{4,}", fix, message)
