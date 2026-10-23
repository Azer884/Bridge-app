"""Check that extracted values are actually supported by the customer's message."""
import re

ONES = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen".split())}
TENS = {w: 10 * i for i, w in enumerate(
    "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if w != "_"}
UNIT_FACTORS = {
    "m": 1.0, "metre": 1.0, "metres": 1.0, "meter": 1.0, "meters": 1.0,
    "cm": 0.01, "centimetre": 0.01, "centimetres": 0.01, "centimeter": 0.01, "centimeters": 0.01,
    "ft": 0.3048, "foot": 0.3048, "feet": 0.3048,
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
        elif tok in ONES:
            if pending_tens is not None and 1 <= ONES[tok] <= 9:
                found.append(float(pending_tens + ONES[tok]))
            else:
                if pending_tens is not None:
                    found.append(float(pending_tens))
                found.append(float(ONES[tok]))
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


_HEDGES = {"about", "around", "roughly", "approximately", "approx"}


def _bare_number(message):
    """The whole message is one number ("6", "five", "about 4.5") with no unit."""
    tokens = [t for t in _TOKEN.findall(str(message).lower()) if t not in _HEDGES]
    return bool(tokens) and all(t[0].isdigit() or t in ONES or t in TENS for t in tokens) \
        and len(numbers_in(message)) == 1


def ground_measurement(value, message):
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
    if not factors and _bare_number(message):
        factors = {1.0}         # a bare number answers a question that asked for metres
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
