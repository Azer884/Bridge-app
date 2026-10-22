"""Input and output safety checks that run in the backend, independent of the model."""
import re

MAX_MESSAGE_CHARS = 1000
MAX_REPLY_CHARS = 600
MAX_STRIKES = 3

REFUSAL = "I can only help with your painting job and quotation."

# Incoming messages that try to steer the model or use it for something else.
_BLOCKED_INPUT = [re.compile(p, re.I) for p in [
    r"\b(ignore|disregard|forget|override|bypass)\b.{0,40}\b(rules?|instructions?|prompts?|guidelines?|restrictions?|checks?)\b",
    r"\b(system|developer|hidden|initial|original) (prompt|message|instructions?)\b",
    r"\byou are now\b",
    r"\bpretend (to be|you are|you're)\b",
    r"\bjailbreak\b|\bdeveloper mode\b|\bDAN mode\b",
    r"\b(write|generate|create|give|show|make)\b.{0,30}\b(code|script|poem|essay|song|joke|program)\b",
    r"\b(python|javascript|typescript|java|c\+\+|sql|html|regex|bash|powershell)\b",
    r"```",
    r"^\s*(system|assistant)\s*:",
]]

# Replies that must never reach a customer.
_BLOCKED_REPLY = re.compile(
    r"```|<script|\bdef \w+\(|\bimport \w+|\bSELECT\b.+\bFROM\b|https?://"
    r"|== [A-H]\.|OUTPUT FORMAT|STATUS VALUES|CURRENT CONTEXT",
    re.I | re.S)


def clip_message(message):
    return message.strip()[:MAX_MESSAGE_CHARS]


def screen_input(message):
    """Return a reason string if the message must not reach the model, else None."""
    for pattern in _BLOCKED_INPUT:
        if pattern.search(message):
            return "blocked_input"
    return None


def reply_problem(reply):
    if len(reply) > MAX_REPLY_CHARS:
        return f"reply is longer than {MAX_REPLY_CHARS} characters"
    if _BLOCKED_REPLY.search(reply):
        return "reply contains code, a link, or internal instructions"
    return None


def clean_profile_name(raw):
    """WhatsApp profile names are user-controlled: keep a plain name or drop it."""
    if not isinstance(raw, str):
        return None
    name = " ".join(raw.split())
    if not 1 <= len(name) <= 40 or not re.fullmatch(r"[^\W\d_][\w'.\- ]*", name):
        return None
    if re.search(r"\d", name):
        return None
    return name


def clean_profile_phone(raw):
    if not isinstance(raw, str):
        return None
    phone = re.sub(r"[^\d+]", "", raw)
    return phone if 7 <= len(re.sub(r"\D", "", phone)) <= 15 else None
