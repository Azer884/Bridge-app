"""Backend checks that hold no matter what the model returns."""
import re
from dataclasses import dataclass, field

from .guard import reply_problem
from .i18n import language_problem
from .grounding import GroundingError, ground_field, numbers_in
from .parsing import ParseError, extract_json
from .schema import FIELDS, STATUS_VALUES, Status

_PRICE = re.compile(r"[$£€]\s?\d|\b\d[\d,.]*\s?(usd|eur|gbp|dollars?|euros?|pounds?)\b", re.I)
_FIGURE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:meters?|metres?|centimet\w+|cm\b|m\b|feet|foot|ft\b|kaki|sq\w*|square)", re.I)
_BOOKING_CLAIM = re.compile(
    r"\b(is|are|has been|have been|been)\s+(booked|confirmed|reserved)\b|\bslot is available\b", re.I)


@dataclass
class ValidationResult:
    problems: list = field(default_factory=list)   # hard: data/contract violations
    soft_problems: list = field(default_factory=list)  # style: reply could be replaced by a template
    ungrounded: list = field(default_factory=list)  # values the customer never stated (also in problems)
    reply: str = ""
    status: str = Status.COLLECTING.value
    accepted: dict = field(default_factory=dict)   # grounded, normalised new values
    conflicts: list = field(default_factory=list)  # (key, old, new)

    @property
    def ok(self):
        return not self.problems and not self.soft_problems


def validate_response(raw_text, state, message, config):
    result = ValidationResult()
    try:
        data = extract_json(raw_text)
    except ParseError as err:
        result.problems.append(str(err))
        return result

    unknown = set(data) - {"reply", "extracted_fields", "missing_fields", "status"}
    missing_keys = {"reply", "extracted_fields", "missing_fields", "status"} - set(data)
    if missing_keys:
        result.problems.append(f"missing JSON keys: {sorted(missing_keys)}")
    if unknown:
        result.problems.append(f"unexpected JSON keys: {sorted(unknown)}")
    if missing_keys:
        return result

    reply, extracted, status = data["reply"], data["extracted_fields"], data["status"]
    empty_reply = isinstance(reply, str) and not reply.strip()
    if not isinstance(reply, str):
        result.problems.append("reply must be a string")
        reply = ""
    if not isinstance(extracted, dict):
        result.problems.append("extracted_fields must be an object")
        extracted = {}
    if not isinstance(data["missing_fields"], list):
        result.problems.append("missing_fields must be a list")
    if status not in STATUS_VALUES:
        result.problems.append(f"invalid status {status!r}; allowed: {STATUS_VALUES}")

    bad_reply = reply_problem(reply)
    if bad_reply:
        result.problems.append(bad_reply)
    if reply.count("?") > 1:
        result.soft_problems.append("reply asks more than one question; ask exactly one")
    wrong_language = language_problem(reply, getattr(state, "lang", "en"))
    if wrong_language:
        result.soft_problems.append(wrong_language)
    if _PRICE.search(reply):
        result.problems.append("reply contains a price; the model must never quote prices")
    if _BOOKING_CLAIM.search(reply):
        result.problems.append("reply claims availability or a booking; it must not")
    invented = invented_figures(reply, state, message)
    if invented:
        result.soft_problems.append(
            f"reply mentions {', '.join(invented)} which the customer never said; do not explain or calculate sizes")

    for key, value in extracted.items():
        spec = FIELDS.get(key)
        if spec is None:
            result.problems.append(f"unknown field key {key!r}")
            continue
        try:
            clean = ground_field(spec, value, message)
        except GroundingError as err:
            if _repeats_verified(spec.kind, state.verified.get(key), value):
                continue  # model echoed an earlier verified value; harmless
            result.problems.append(f"{key}: {err}")
            result.ungrounded.append(f"{key}: {err}")
            continue
        old = state.verified.get(key)
        if old is not None and not _same(spec.kind, old, clean):
            result.conflicts.append((key, old, clean))
        else:
            result.accepted[key] = clean

    if empty_reply and state.missing_required(config, extra=result.accepted):
        result.problems.append("reply must not be empty")

    if status in STATUS_VALUES:
        still_missing = state.missing_required(config, extra=result.accepted)
        if status == Status.READY.value and still_missing:
            result.problems.append(f"status ready_for_estimate but still missing: {still_missing}")

    if status in (Status.COLLECTING.value, Status.CLARIFICATION.value):
        asked = _fields_asked_about(reply, state.missing_required(config, extra=result.accepted))
        if len(asked) > 1:
            result.soft_problems.append(f"reply asks about several fields at once {asked}; ask about one")
        elif asked:
            first = state.missing_required(config, extra=result.accepted)[0]
            if asked[0] != first:
                result.soft_problems.append(f"reply asks about {asked[0]} but the next missing field is {first}")

    result.reply, result.status = reply, status
    return result


def invented_figures(reply, state, message):
    """Sizes in the reply that are not the customer's own ("from the perimeter being 16 meters..."), which the model
    made up. A size is fine when the customer said it, in this message or earlier, or it is a size already saved."""
    allowed = set(numbers_in(message))
    for turn in getattr(state, "history", []):
        if turn.get("role") == "user":
            allowed.update(numbers_in(turn.get("content", "")))
    for value in state.verified.values():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            allowed.update({float(value), round(float(value), 1), round(float(value), 2)})
    found = []
    for match in _FIGURE.finditer(reply):
        number = float(match.group(1).replace(",", "."))
        if not any(abs(number - a) < 0.051 for a in allowed):
            found.append(match.group(0).strip())
    return found


# Words that signal the reply is asking for a particular field.
_ASK_WORDS = {
    "customer_name": ["name"], "phone": ["phone", "number", "contact"], "email": ["email"],
    "address": ["address"], "surfaces": ["surfaces"],
    "room_length_m": ["length", "long"], "room_width_m": ["width", "wide"],
    "room_height_m": ["height", "high", "tall"], "preferred_datetime": ["date", "time", "day"],
}


def _fields_asked_about(reply, missing):
    words = set(re.findall(r"[a-z]+", reply.lower()))
    return [k for k in missing if words & set(_ASK_WORDS.get(k, []))]


def _repeats_verified(kind, old, value):
    if old is None:
        return False
    if kind == "list":
        return all(v in old for v in ([value] if isinstance(value, str) else value))
    return str(old).strip().lower() == str(value).strip().lower()


def _same(kind, old, new):
    if kind == "list":
        return True  # new surfaces extend the list; not a conflict
    if kind == "measurement":
        return abs(old - new) < 0.01
    return str(old).strip().lower() == str(new).strip().lower()
