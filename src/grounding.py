"""Check that extracted values are actually supported by the customer's message."""
import re

ONES = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen".split())}
# Malay number words (satu .. sepuluh, sebelas); "dua belas" and bigger are left to digits
ONES.update({"kosong": 0, "sifar": 0, "satu": 1, "dua": 2, "tiga": 3, "empat": 4, "lima": 5, "enam": 6,
             "tujuh": 7, "lapan": 8, "sembilan": 9, "sepuluh": 10, "sebelas": 11})
TENS = {w: 10 * i for i, w in enumerate(
    "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if w != "_"}
ORDINALS = {"third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10}
UNIT_FACTORS = {
    "m": 1.0, "metre": 1.0, "metres": 1.0, "meter": 1.0, "meters": 1.0,
    "cm": 0.01, "centimetre": 0.01, "centimetres": 0.01, "centimeter": 0.01, "centimeters": 0.01,
    "ft": 0.3048, "foot": 0.3048, "feet": 0.3048, "kaki": 0.3048,
}
_TOKEN = re.compile(r"\d+(?:[.,]\d+)?|[a-z]+")


class GroundingError(ValueError):
    pass


def numbers_in(text):
    """Numbers written as digits or English words (0-99)."""
    found = []
    pending_tens = None
    for tok in _TOKEN.findall(str(text).lower()):
        if tok[0].isdigit():
            found.append(float(tok.replace(",", ".")))
            pending_tens = None
        elif tok in TENS:
            if pending_tens is not None:
                found.append(float(pending_tens))
            pending_tens = TENS[tok]
        elif tok in ONES or tok in ORDINALS:
            value = ONES[tok] if tok in ONES else ORDINALS[tok]      # "seventh" is what speech-to-text writes for "seven"
            if pending_tens is not None and 1 <= value <= 9:
                found.append(float(pending_tens + value))
            else:
                if pending_tens is not None:
                    found.append(float(pending_tens))
                found.append(float(value))
            pending_tens = None
        else:
            if pending_tens is not None:
                found.append(float(pending_tens))
            pending_tens = None
    if pending_tens is not None:
        found.append(float(pending_tens))
    return found


def unit_factors_in(text):
    return {UNIT_FACTORS[t] for t in _TOKEN.findall(str(text).lower()) if t in UNIT_FACTORS}


def norm(text):
    return re.sub(r"[^a-z0-9@+ ]+", " ", str(text).lower()).split()


HEDGES = _HEDGES = {"about", "around", "roughly", "approximately", "approx", "maybe", "perhaps", "probably", "say",
           "lets", "let", "s", "its", "it", "is", "i", "think", "guess", "like", "around", "over", "under",
           "just", "estimate", "estimation", "the", "a", "be", "would", "should", "might", "or", "so"}
_RANGE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:to|-|or|and)\s*(\d+(?:[.,]\d+)?)", re.I)
ESTIMATE_WORDS = re.compile(
    r"\b(maybe|about|around|roughly|approx\w*|say|guess|ig|think|probably|estimat\w*|not sure|not exactly)\b",
    re.I)


def estimate_in(message):
    """(upper_bound, is_estimate): "4 to 5 m" -> 5, so the quote is never short; hedged answers are flagged."""
    match = _RANGE.search(str(message))
    if match:
        return max(float(match.group(1).replace(",", ".")), float(match.group(2).replace(",", "."))), True
    return None, bool(ESTIMATE_WORDS.search(str(message)))


_NUM = r"\d+(?:[.,]\d+)?|" + "|".join(sorted((w for w in ONES if w != "zero"), key=len, reverse=True))
_U = r"(?:\s*(?:metres?|meters?|meter|cm|ft|feet|foot|kaki|m\b))?"          # a unit may follow each number
_SIZES = re.compile(rf"\b({_NUM}){_U}\s*(?:x|by|\*|kali)\s*({_NUM}){_U}(?:\s*(?:x|by|\*|kali)\s*({_NUM}){_U})?", re.I)


_SPACED = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)[\s,]+(\d+(?:[.,]\d+)?)(?:[\s,]+(\d+(?:[.,]\d+)?))?(?![\w.])")
_PIECE_SPLIT = re.compile(r"\s*(?:x|by|\*|kali)\s*", re.I)


def sizes_metric(message):
    """Sizes written with their own units ("10ft x 3m", "12 kaki kali 10 kaki"), in metres, or None. A unit written
    once at the end ("4 x 5 m") counts for the numbers before it."""
    match = _SIZES.search(str(message))
    if not match:
        return None
    parts = [(numbers_in(p), unit_factors_in(p)) for p in _PIECE_SPLIT.split(match.group(0))]
    shared = next((next(iter(f)) for _, f in reversed(parts) if len(f) == 1), None)
    out = []
    for numbers, factors in parts:
        factor = next(iter(factors)) if len(factors) == 1 else shared
        if not numbers or factor is None:
            return None
        out.append(round(numbers[0] * factor, 3))
    return out


def sizes_in(message, loose=False):
    """"4 by 5" or "3x4x2.5": the numbers, in the order written (two or three of them), else None.
    `loose` also reads numbers just set side by side ("walls 4 4 3") when a room is being measured."""
    match = _SIZES.search(str(message))
    if not match:
        spaced = _SPACED.search(str(message)) if loose else None
        if not spaced:
            return None
        values = [float(g.replace(",", ".")) for g in spaced.groups() if g]
        return values if all(0.3 <= v <= 100 for v in values) else None
    return [numbers_in(g)[0] for g in match.groups() if g and numbers_in(g)]


_CUE_KEYS = {"height": "room_height_m", "tall": "room_height_m", "high": "room_height_m", "tinggi": "room_height_m",
             "length": "room_length_m", "long": "room_length_m", "panjang": "room_length_m",
             "width": "room_width_m", "wide": "room_width_m", "lebar": "room_width_m"}
_CUE_WORD = re.compile(r"\b(" + "|".join(_CUE_KEYS) + r")\b", re.I)
_UNIT_WORD = r"(m\b|metres?|meters?|meter|cm|ft|feet|foot|kaki)"
_AMOUNT = re.compile(rf"\b({_NUM})(?:\s*{_UNIT_WORD})?", re.I)
_DECIMAL = re.compile(rf"\b({_NUM})\s+(?:point|dot|titik)\s+({_NUM})\b", re.I)


def spoken_decimals(text):
    """"three point five" or "3 point 5" is 3.5, which is how callers and voice notes say a size."""
    def join(match):
        whole, part = numbers_in(match.group(1)), numbers_in(match.group(2))
        return f"{whole[0]:g}.{int(part[0])}" if whole and part else match.group(0)
    return _DECIMAL.sub(join, text)


_PERIMETER = re.compile(rf"perim\w*\D{{0,12}}({_NUM})\s*(m\b|metres?|meters?|meter|cm|ft|feet|kaki)?", re.I)


def _to_metres(number, unit, plain=(1.5, 8.0)):
    """A number and the unit written after it (or none, which counts as metres only for a room-sized figure)."""
    value = numbers_in(number)[0]
    if unit:
        factors = unit_factors_in(unit)
        return round(value * next(iter(factors)), 3) if len(factors) == 1 else None
    return value if plain[0] <= value <= plain[1] else None


def cued_sizes(message):
    """Sizes tied to a word in the sentence: "height of 3 meters", "4 m long", and a square room's perimeter
    ("perimeter is 16 metres", "square" gives 4 m a side). {room_*_m: metres}; only believable values."""
    found = {}
    cues = [(m.start(), m.end(), _CUE_KEYS[m.group(1).lower()]) for m in _CUE_WORD.finditer(message)]
    amounts = [(m.start(), m.end(), m.group(1), m.group(2)) for m in _AMOUNT.finditer(message)]
    taken = set()
    for i, (start, end, key) in enumerate(cues):
        if i + 1 < len(cues) and not re.search(r"\d", message[end:cues[i + 1][0]]) \
                and re.fullmatch(r"[\s,x*&]*(?:by|and|kali|dan)?[\s,x*&]*", message[end:cues[i + 1][0]], re.I):
            return {}                   # "length x width is 5 by 3": the words only name the order, the sizes follow
        limit = cues[i + 1][0] if i + 1 < len(cues) else len(message)
        floor = cues[i - 1][1] if i else 0
        before = [a for a in amounts if floor <= a[0] and a[1] <= start and start - a[1] <= 3 and a[0] not in taken
                  and not message[a[1]:start].strip()]            # "4 m long", never "4 meters, height 3"
        after = [a for a in amounts if end <= a[0] < limit and a[0] - end <= 16 and a[0] not in taken
                 and not re.search(r"\d", message[end:a[0]])]
        pick = before[-1] if before else (after[0] if after else None)
        if pick is None:
            continue
        taken.add(pick[0])
        metres = _to_metres(pick[2], pick[3])
        if metres and 0.3 <= metres <= 100:
            found[key] = metres
    perimeter = _PERIMETER.search(message)
    if perimeter and re.search(r"\bsquare\b", message, re.I):
        side = _to_metres(perimeter.group(1), perimeter.group(2), plain=(4.0, 40.0))
        if side and 1.0 <= side / 4 <= 25:
            found.setdefault("room_length_m", round(side / 4, 3))
            found.setdefault("room_width_m", round(side / 4, 3))
    return found


def _bare_number(message):
    """The whole message is one number ("6", "five", "about 4.5") with no unit."""
    tokens = [t for t in _TOKEN.findall(str(message).lower()) if t not in _HEDGES]
    return bool(tokens) and all(t[0].isdigit() or t in ONES or t in TENS for t in tokens) \
        and len(numbers_in(message)) == 1


def ground_measurement(value, message, assume_metres=False):
    """Return metres, or raise GroundingError if unsupported or the unit is unclear."""
    if isinstance(value, bool) or value is None:
        raise GroundingError("not a measurement")
    if isinstance(value, (int, float)):
        number, factors = float(value), set()
    else:
        nums = numbers_in(value)
        if len(nums) != 1:
            raise GroundingError(f"cannot read one number from {value!r}")
        number, factors = nums[0], unit_factors_in(value)
    if number not in numbers_in(message):
        raise GroundingError(f"{value!r} was not stated by the customer")
    if not factors:
        factors = unit_factors_in(message)
    if not factors and (_bare_number(message) or assume_metres):
        factors = {1.0}         # a number answers a question that asked for metres
    if len(factors) != 1:
        raise GroundingError(f"unit unclear for {value!r}; ask the customer for the unit")
    metres = round(number * factors.pop(), 3)
    if not 0.3 <= metres <= 100:
        raise GroundingError(f"{value!r} is outside a plausible range")
    return metres


STOPWORDS = {"the", "a", "an", "and", "my", "of", "to", "is", "it", "its", "just", "only"}


def ground_text(value, message):
    """Every meaningful word of the value must appear in the message (order and filler may differ)."""
    if not isinstance(value, str) or not value.strip():
        raise GroundingError(f"{value!r} is not a text value")
    if len(value) > 200:
        raise GroundingError("value is too long")
    words = [w for w in norm(value) if w not in STOPWORDS]
    if not words or not set(words) <= set(norm(message)):
        raise GroundingError(f"{value!r} was not stated by the customer")
    return value.strip()


def ground_phone(value, message):
    digits = re.sub(r"\D", "", str(value))
    if len(digits) < 7 or digits not in re.sub(r"\D", "", message):
        raise GroundingError(f"phone {value!r} was not stated by the customer")
    return str(value).strip()


def ground_email(value, message):
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", str(value).strip()):
        raise GroundingError(f"{value!r} is not an email address")
    if str(value).strip().lower() not in message.lower():
        raise GroundingError(f"email {value!r} was not stated by the customer")
    return str(value).strip()


def ground_list(value, message):
    items = re.split(r"\s*(?:,|&|\band\b)\s*", value) if isinstance(value, str) else value
    items = [i for i in items if isinstance(i, str) and i.strip()] if isinstance(items, list) else items
    if not isinstance(items, list) or not items:
        raise GroundingError(f"{value!r} is not a list")
    return [ground_text(item, message) for item in items]


def ground_field(spec, value, message):
    return {
        "measurement": ground_measurement,
        "phone": ground_phone,
        "email": ground_email,
        "list": ground_list,
    }.get(spec.kind, ground_text)(value, message)
