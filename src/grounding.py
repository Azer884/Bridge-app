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


def sizes_in(message):
    """"4 by 5" or "3x4x2.5": the numbers, in the order written (two or three of them), else None."""
    match = _SIZES.search(str(message))
    if not match:
        return None
    return [numbers_in(g)[0] for g in match.groups() if g and numbers_in(g)]


_CUED = {
    "room_height_m": re.compile(rf"(?:height|tall|high|tinggi)\D{{0,14}}?({_NUM})\s*(m\b|metres?|meters?|meter|cm|ft|feet|kaki)?|"
                                rf"\b({_NUM})\s*(m\b|metres?|meters?|meter|cm|ft|feet|kaki)?\s*(?:high|tall|tinggi)\b", re.I),
    "room_length_m": re.compile(rf"(?:length|long|panjang)\D{{0,14}}?({_NUM})\s*(m\b|metres?|meters?|meter|cm|ft|feet|kaki)?|"
                                rf"\b({_NUM})\s*(m\b|metres?|meters?|meter|cm|ft|feet|kaki)?\s*(?:long|panjang)\b", re.I),
    "room_width_m": re.compile(rf"(?:width|wide|lebar)\D{{0,14}}?({_NUM})\s*(m\b|metres?|meters?|meter|cm|ft|feet|kaki)?|"
                               rf"\b({_NUM})\s*(m\b|metres?|meters?|meter|cm|ft|feet|kaki)?\s*(?:wide|lebar)\b", re.I),
}
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
    found, where = {}, {}
    for key, pattern in _CUED.items():
        match = pattern.search(message)
        if match:
            group = 1 if match.group(1) else 3
            number, unit = match.group(group), match.group(group + 1)
            metres = _to_metres(number, unit)
            if metres and 0.3 <= metres <= 100:
                found[key], where[key] = metres, match.start(group)
    for key in [k for k in found if list(where.values()).count(where[k]) > 1]:
        del found[key]                  # two words reached for the same number ("length x width is 5 by 3"): not tied
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
