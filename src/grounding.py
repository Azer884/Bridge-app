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
_UNIT_WORD = r"(m\b|metres?|meters?|meter|centimet\w+|cm|ft|feet|foot|kaki)"
_AMOUNT = re.compile(rf"\b({_NUM})(?:\s*{_UNIT_WORD})?", re.I)
_DECIMAL = re.compile(rf"\b({_NUM})\s+(?:point|dot|titik)\s+({_NUM})\b", re.I)


def spoken_decimals(text):
    """"three point five" or "3 point 5" is 3.5, which is how callers and voice notes say a size."""
    def join(match):
        whole, part = numbers_in(match.group(1)), numbers_in(match.group(2))
        return f"{whole[0]:g}.{int(part[0])}" if whole and part else match.group(0)
    return _DECIMAL.sub(join, text)


_HALF = re.compile(rf"\b({_NUM})\s+and\s+a\s+half\b", re.I)
_HUNDRED = re.compile(r"\b(\d+|one|two|three|four|five|six|seven|eight|nine)\s+hundred\b(?:\s+(?:and\s+)?((?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[\s-](?:one|two|three|four|five|six|seven|eight|nine))?"
                      r"|(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen))\b)?", re.I)
_UNIT_DOT = re.compile(r"\b(m|cm|mm|ft)\.(?=\s|$)", re.I)                      # "5 m. long": speech-to-text ends the unit with a dot
_UNIT_HYPHEN = re.compile(r"(?<=\w)-(?=(?:meters?|metres?|feet|foot|ft|cm|centimet\w+|m)\b)", re.I)   # "five-meter long"
_IN_CUE = re.compile(r"\bin\s+(length|width|height)\b", re.I)
_IN_CUE_WORD = {"length": "long", "width": "wide", "height": "high"}


def spoken_sizes(text):
    """How speech-to-text and people on a call write sizes, turned into what the readers expect: "three point five" and
    "five and a half" are 3.5 and 5.5, "five hundred centimeters" is 500, "5 m." and "five-meter" lose the dot and hyphen,
    and "five meters in length" is "five meters long"."""
    text = spoken_decimals(str(text))

    def half(match):
        whole = numbers_in(match.group(1))
        return f"{whole[0]:g}.5" if whole else match.group(0)

    def hundred(match):
        head = numbers_in(match.group(1))
        if not head:
            return match.group(0)
        total = head[0] * 100
        if match.group(2):
            tail = numbers_in(match.group(2))
            if len(tail) != 1:
                return f"{total:g} {match.group(2)}"
            total += tail[0]
        return f"{total:g}"

    text = _HALF.sub(half, text)
    text = _HUNDRED.sub(hundred, text)
    text = _UNIT_DOT.sub(lambda m: m.group(1), text)
    text = _UNIT_HYPHEN.sub(" ", text)
    return _IN_CUE.sub(lambda m: _IN_CUE_WORD[m.group(1).lower()], text)


# --- the rest of what people say aloud: phone numbers, dates, street numbers ------------------------------------------------
_DIGIT_WORDS = {"zero": "0", "oh": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7",
                "eight": "8", "nine": "9"}
_DIGIT_RUN = re.compile(r"(?:\bplus\s+)?(?:\b(?:double|triple)\s+)?\b(?:" + "|".join(_DIGIT_WORDS) + r")\b"
                        r"(?:[\s,.\-]+(?:(?:double|triple)\s+)?(?:" + "|".join(_DIGIT_WORDS) + r")\b){5,}", re.I)


def spoken_digits(text):
    """"zero one two three four five six seven eight nine" or "oh one two, double three ..." is a phone number: a run of at
    least six digit words becomes digits ("plus six zero ..." keeps its plus). Shorter runs are left alone."""
    def join(match):
        out, repeat = [], 1
        for word in re.findall(r"plus|double|triple|[a-z]+", match.group(0).lower()):
            if word == "plus":
                out.append("+")
            elif word in ("double", "triple"):
                repeat = 2 if word == "double" else 3
            elif word in _DIGIT_WORDS:
                out.append(_DIGIT_WORDS[word] * repeat)
                repeat = 1
        digits = "".join(out)
        return digits if len(digits.lstrip("+")) >= 7 else match.group(0)
    return _DIGIT_RUN.sub(join, text)


_ORDINAL_WORDS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8,
                  "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14, "fifteenth": 15,
                  "sixteenth": 16, "seventeenth": 17, "eighteenth": 18, "nineteenth": 19, "twentieth": 20, "thirtieth": 30}
_ORDINAL_TENS = {"twenty": 20, "thirty": 30}
_DAY_WORD = (r"(?:(?:twenty|thirty)[\s-](?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth)|" + "|".join(_ORDINAL_WORDS)
             + r"|(?:twenty|thirty)(?:[\s-](?:one|two|three|four|five|six|seven|eight|nine))?|" + "|".join(w for w in ONES if w.isascii() and w != "zero")
             + r"|\d{1,2}(?:st|nd|rd|th)?)")
_MONTHS_SPOKEN = (r"(?:january|jan|february|feb|march|mar|april|apr|may|june|jun|july|jul|august|aug|september|sept|sep|october|oct|"
                  r"november|nov|december|dec)")
_THE_OF = re.compile(rf"\b(?:the\s+)?({_DAY_WORD})\s+(?:of\s+)({_MONTHS_SPOKEN})\b", re.I)
_MONTH_THE = re.compile(rf"\b({_MONTHS_SPOKEN})\s+(?:the\s+)?({_DAY_WORD})\b", re.I)
_MONTHS_NO_MAY = _MONTHS_SPOKEN.replace("may|", "")                 # "five may be enough" is not the 5th of May
_WORD_MONTH = re.compile(rf"\b({_DAY_WORD})\s+({_MONTHS_NO_MAY})\b", re.I)
_HOUR_WORD = re.compile(r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s*(a\.?m\.?|p\.?m\.?)(?=\W|$)", re.I)
_AMPM_DOTS = re.compile(r"\b([ap])\.m\.?(?=\W|$)", re.I)
_STREET_WORDS = (r"(?:jalan|jln|lorong|lrg|lebuh|persiaran|lengkok|taman|tmn|bandar|kampung|kg|block|blok|lot|unit|no|number)")


def _day_number(word):
    """The day a spoken day word means ("fifth", "twenty first", "5th", "five"), or None."""
    word = word.lower().strip()
    digits = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?", word)
    if digits:
        return int(digits.group(1))
    if word in _ORDINAL_WORDS:
        return _ORDINAL_WORDS[word]
    parts = re.split(r"[\s-]+", word)
    if parts[0] in _ORDINAL_TENS:
        if len(parts) == 1:
            return _ORDINAL_TENS[parts[0]]
        tail = _ORDINAL_WORDS.get(parts[1]) or ONES.get(parts[1])
        return _ORDINAL_TENS[parts[0]] + tail if tail else None
    return ONES.get(word)


def spoken_dates(text):
    """"the fifth of November", "November the fifth", "five November" are "5 November" and "November 5"; "ten a.m." is
    "10 am" and "p.m." is "pm"."""
    def day_month(match):
        day = _day_number(match.group(1))
        return f"{day} {match.group(2)}" if day is not None else match.group(0)       # 32 stays: it is then refused as a date that does not exist

    def month_day(match):
        day = _day_number(match.group(2))
        return f"{match.group(1)} {day}" if day is not None else match.group(0)

    def hour(match):
        return f"{ONES[match.group(1).lower()]} {match.group(2)[0].lower()}m"

    text = _THE_OF.sub(day_month, text)
    text = _WORD_MONTH.sub(day_month, text)
    text = _MONTH_THE.sub(month_day, text)
    text = _HOUR_WORD.sub(hour, text)
    return _AMPM_DOTS.sub(lambda m: m.group(1).lower() + "m", text)


_STREET_NUMBER_WORDS = re.compile(
    rf"\b((?:(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)[\s-]?)?(?:one|two|three|four|five|six|seven|eight|nine|ten|"
    rf"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen)|(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety))"
    rf"(?=\s+{_STREET_WORDS}\b)", re.I)
_SECTION_WORDS = re.compile(rf"\b(ss|usj|pju|section|seksyen)\s+({_DAY_WORD})(?:\s+(?:slash|stroke|over)\s+({_DAY_WORD}))?", re.I)


def spoken_places(text):
    """"twelve Jalan Ampang" and "twenty five Jalan SS two slash three" are 12 and 25 Jalan SS 2/3."""
    def number(match):
        words = match.group(1).lower()
        value = [numbers for numbers in numbers_in(words)]
        return f"{value[0]:g}" if len(value) == 1 else match.group(0)

    def section(match):
        first = _day_number(match.group(2))
        second = _day_number(match.group(3)) if match.group(3) else None
        if first is None:
            return match.group(0)
        return f"{match.group(1)} {first}" + (f"/{second}" if second is not None else "")

    return _SECTION_WORDS.sub(section, _STREET_NUMBER_WORDS.sub(number, text))


_HOUR_W = r"(?:twelve|eleven|ten|nine|eight|seven|six|five|four|three|two|one|\d{1,2})"
_PART_AFTER = r"(?:\s+(?:in\s+the\s+|at\s+)?(?P<part>morning|afternoon|evening|night)\b|\s*(?P<ap>[ap])\.?m\b\.?)?"
_MIN_W = r"(?:five|ten|twenty[\s-]five|twenty|fifteen|thirty|forty[\s-]five)"
_HALF_QUARTER = re.compile(rf"\b(half|quarter)\s+(past|to)\s+({_HOUR_W})\b{_PART_AFTER}", re.I)
_MIN_PAST_TO = re.compile(rf"\b({_MIN_W})\s+(past)\s+({_HOUR_W})\b{_PART_AFTER}", re.I)     # "to" is left: "five to ten" is a range
_OCLOCK = re.compile(rf"\b({_HOUR_W})\s+o'?\s?clock\b{_PART_AFTER}", re.I)
_HOUR_MIN = re.compile(rf"\b(?:at\s+)?({_HOUR_W})\s+(thirty|fifteen|forty[\s-]five)\b{_PART_AFTER}", re.I)
_MINUTES_OF = {"thirty": 30, "fifteen": 15, "forty five": 45, "forty-five": 45}


def _hour_number(word):
    word = word.lower()
    return int(word) if word.isdigit() else ONES.get(word)


def _clock(hour, minute, part):
    """H:MM for a time said aloud. A part of the day makes it am or pm; without one, 1 to 6 means the afternoon (the crew works
    9 to 6), and 7 to 12 is left as it is."""
    if hour is None or not 1 <= hour <= 12 or not 0 <= minute < 60:
        return None
    if part:
        pm = part.lower() != "morning" and not (hour == 12 and part.lower() == "morning")
        pm = pm and hour != 12 or (hour == 12 and part.lower() != "morning")
        suffix = " pm" if pm else " am"
        return f"{hour}:{minute:02d}{suffix}"
    return f"{hour}:{minute:02d} pm" if 1 <= hour <= 6 else f"{hour}:{minute:02d}"


def _part(match):
    """"morning" or "afternoon" from what followed a time said aloud ("in the morning", "pm"), or None."""
    if match.group("part"):
        return match.group("part")
    if match.group("ap"):
        return "morning" if match.group("ap").lower() == "a" else "afternoon"
    return None


def spoken_times(text):
    """"half past two", "quarter to three", "ten past nine", "two o'clock" and "at two thirty" as 2:30 pm, 2:45 pm, 9:10, 2:00 pm."""
    def half_quarter(match):
        hour = _hour_number(match.group(3))
        if hour is None:
            return match.group(0)
        kind, direction = match.group(1).lower(), match.group(2).lower()
        if direction == "past":
            minute, base = (30 if kind == "half" else 15), hour
        elif kind == "quarter":
            minute, base = 45, (hour - 1) or 12
        else:
            return match.group(0)                                   # "half to" is not a time
        return _clock(base, minute, _part(match)) or match.group(0)

    def min_past_to(match):
        minutes = numbers_in(match.group(1).replace("-", " "))
        hour = _hour_number(match.group(3))
        if not minutes or hour is None:
            return match.group(0)
        minute = int(minutes[0])
        if match.group(2).lower() == "to":
            minute, hour = 60 - minute, (hour - 1) or 12
        return _clock(hour, minute, _part(match)) or match.group(0)

    def oclock(match):
        return _clock(_hour_number(match.group(1)), 0, _part(match)) or match.group(0)

    def hour_min(match):
        minute = _MINUTES_OF.get(re.sub(r"\s+", " ", match.group(2).lower().replace("-", " ")).replace(" ", "-")) \
            or _MINUTES_OF.get(match.group(2).lower().replace("-", " "))
        if not _part(match) and not match.group(0).lower().startswith("at "):
            return match.group(0)                                   # "two thirty" alone could be a size: it needs "at", am or pm
        return _clock(_hour_number(match.group(1)), minute or 0, _part(match)) or match.group(0)

    text = _HALF_QUARTER.sub(half_quarter, text)
    text = _MIN_PAST_TO.sub(min_past_to, text)
    text = _OCLOCK.sub(oclock, text)
    return _HOUR_MIN.sub(hour_min, text)


def normalise_speech(text):
    """Everything said aloud that the readers expect written: sizes, phone numbers, dates, street numbers."""
    return spoken_places(spoken_times(spoken_dates(spoken_digits(spoken_sizes(text)))))


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
