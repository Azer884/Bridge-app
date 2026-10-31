"""End-of-conversation contact step. Deterministic: no model involved.

Name and phone come from the messaging channel (WhatsApp). The customer is only asked
to confirm them, to change them, or to supply whichever one the channel did not provide.
"""
import re

from .i18n import t

AFFIRMATIVE = {"yes", "yeah", "yep", "yup", "ok", "okay", "sure", "correct", "right",
               "confirm", "confirmed", "fine", "good", "perfect", "please", "ya", "yea",
               "ye", "betul", "boleh", "setuju", "okey", "baik", "sila", "bagus", "tepat", "same", "sama"}
NEGATIVE = {"no", "nope", "nah", "wrong", "different", "change", "tak", "tidak", "bukan", "salah", "tukar",
            "lain", "taknak"}
_NOT_NAMES = AFFIRMATIVE | NEGATIVE | {"the", "same", "my", "it", "a", "an", "this", "that", "thanks",
                                       "thank", "you", "and", "number", "name", "phone", "sama", "nama",
                                       "nombor", "terima", "kasih"}
_ABUSIVE = {"fuck", "fucking", "shit", "bitch", "asshole", "dick", "pussy", "cunt", "bastard", "idiot",
            "stupid", "babi", "sial", "bodoh", "anjing", "pukimak", "puki", "celaka", "bangsat", "tolol",
            "kimak", "lancau", "keparat"}
# words customers send that are not a name (greetings, commands, laughter)
_CHATTER = {"idk", "dunno", "skip", "whatever", "nothing", "none", "anything", "any", "order", "again", "wait", "hold",
            "what's", "whats", "when's", "where's", "who's", "how's", "why's", "pass", "nope", "no", "yes", "okay", "ok",
            "hello", "hi", "hey", "stop", "cancel", "lol", "haha", "hahaha", "what", "why", "how", "when",
            "where", "who", "help", "test", "testing", "baby", "bye", "hmm", "please", "later", "tomorrow",
            "today", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
            "helo", "hai", "apa", "kenapa", "bila", "mana", "siapa", "tolong", "esok", "lusa", "nanti",
            "isnin", "selasa", "rabu", "khamis", "jumaat", "sabtu", "ahad", "sayang", "selamat"}
_NAME_AFTER = re.compile(
    r"(?:under|name is|name's|call me|i am|i'm|this is|in the name of|use|atas nama|nama saya|nama aku|it's|its|it is|"
    r"panggil saya|saya ialah|guna)\s+"
    r"([^\W\d_][\w'\-]*(?:\s+[^\W\d_][\w'\-]*){0,2})", re.I)
_PHONE_TALK = {"use", "instead", "change", "number", "phone", "new", "my", "is", "the", "call", "me", "at", "on",
               "whatsapp", "contact", "reach", "text", "number:", "tel", "mobile", "hp"}
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
        return t("contact_confirm", state.lang, name=name, phone=phone)
    if not name:
        state.contact_step = "ask_name"
        return t("contact_ask_name", state.lang)
    state.contact_step = "ask_phone"
    return t("contact_ask_phone", state.lang)


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
        bare = message.strip()
        without_phone = re.sub(r"\+?\d[\d\s().\-]{5,}\d", " ", bare).strip(" ,.")
        if without_phone != bare and set(_words(without_phone)) & _PHONE_TALK:
            without_phone = ""                  # "use 555 123 4567 instead" has no name in it
        if without_phone and without_phone != bare:
            bare = without_phone                # "Siti 0123456789": the name is what is left
        if re.fullmatch(r"[^\W\d_][\w'\-]*(?:\s+[^\W\d_][\w'\-]*){0,3}", bare):
            candidate = bare
    if not candidate:
        return None
    words = candidate.split()
    from .answers import _NOT_AN_INTRO          # "yes I'm doctor", "I'm busy": a job or a state, not a name
    if words[0].lower() in _NOT_NAMES or words[0].lower() in _NOT_AN_INTRO or len(candidate) > 40:
        return None
    if (_ABUSIVE | _CHATTER) & set(_words(candidate)):
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
            and not find_phone(message) and not find_name(message, False):
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
    return t("contact_done", state.lang, name=name, phone=phone)
