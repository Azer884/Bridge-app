"""End-of-conversation contact step. Deterministic: no model involved.

Name and phone come from the messaging channel (WhatsApp). The customer is only asked
to confirm them, to change them, or to supply whichever one the channel did not provide.
"""
import re

AFFIRMATIVE = {"yes", "yeah", "yep", "yup", "ok", "okay", "sure", "correct", "right",
               "confirm", "confirmed", "fine", "good", "perfect", "please", "ya", "yea"}
NEGATIVE = {"no", "nope", "nah", "wrong", "different", "change"}
_NOT_NAMES = AFFIRMATIVE | NEGATIVE | {"the", "same", "my", "it", "a", "an", "this", "that", "thanks",
                                       "thank", "you", "and", "number", "name", "phone"}
_NAME_AFTER = re.compile(
    r"(?:under|name is|name's|call me|i am|i'm|this is|in the name of|use)\s+"
    r"([^\W\d_][\w'\-]*(?:\s+[^\W\d_][\w'\-]*){0,2})", re.I)
_PHONE = re.compile(r"\+?\d[\d\s().\-]{5,}\d")

DONE_REPLY = "Thanks! Our team has your details and will be in touch to confirm everything."


def known_contact(state):
    name = state.verified.get("customer_name") or state.channel.get("name")
    phone = state.verified.get("phone") or state.channel.get("phone")
    return name, phone


def begin(state):
    state.stage = "contact"
    return _prompt(state)


def _prompt(state):
    name, phone = known_contact(state)
    if name and phone:
        state.contact_step = "confirm"
        return (f"Shall I reserve this under {name} and {phone}? Reply yes, or send me the "
                "name or number you'd like to use instead.")
    if not name:
        state.contact_step = "ask_name"
        return "What name should the booking be under?"
    state.contact_step = "ask_phone"
    return "What phone number should we use for the booking?"


def find_phone(message):
    match = _PHONE.search(message)
    if not match:
        return None
    phone = re.sub(r"[^\d+]", "", match.group())
    return phone if 7 <= len(re.sub(r"\D", "", phone)) <= 15 else None


def find_name(message, allow_bare):
    match = _NAME_AFTER.search(message)
    candidate = match.group(1) if match else None
    if candidate is None and allow_bare:
        if re.fullmatch(r"[^\W\d_][\w'\-]*(?:\s+[^\W\d_][\w'\-]*){0,3}", message.strip()):
            candidate = message.strip()
    if not candidate:
        return None
    words = candidate.split()
    if words[0].lower() in _NOT_NAMES or len(candidate) > 40:
        return None
    return " ".join(w.capitalize() if w.islower() else w for w in words)


def _words(message):
    return re.findall(r"[a-z']+", message.lower())


def handle_reply(state, message):
    """Return (reply, finished)."""
    words = _words(message)
    step = state.contact_step
    if step == "confirm" and words and words[0] in NEGATIVE and not find_phone(message) \
            and not find_name(message, False):
        state.channel = {}                      # the customer rejected the channel details
        state.verified.pop("customer_name", None)
        state.verified.pop("phone", None)
        return _prompt(state), False

    if step == "confirm" and words and words[0] in AFFIRMATIVE and len(words) <= 4 \
            and not find_phone(message):
        return _finish(state, *known_contact(state)), True

    new_phone = find_phone(message) if step in ("confirm", "ask_phone") else None
    new_name = find_name(message, allow_bare=step in ("confirm", "ask_name"))
    if step == "ask_phone":
        new_name = None
    if step == "ask_name" and find_phone(message):
        new_phone = find_phone(message)     # "Karim, 555 123 4567" in one go
    if not new_name and not new_phone:
        return _prompt(state), False
    if new_name:
        state.verified["customer_name"] = new_name
    if new_phone:
        state.verified["phone"] = new_phone
    name, phone = known_contact(state)
    if name and phone:
        return _finish(state, name, phone), True
    return _prompt(state), False


def _finish(state, name, phone):
    state.verified["customer_name"], state.verified["phone"] = name, phone
    state.stage = "done"
    return (f"Perfect, I've noted the booking under {name}, {phone}. We'll prepare your "
            "quotation and a team member will confirm your appointment.")
