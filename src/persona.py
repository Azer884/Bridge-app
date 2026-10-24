"""Customer-facing characters. A persona changes tone and a few fixed phrases only: the permanent
rules, field order, validation and pricing never depend on it."""
import re

from .guard import screen_input

ID_PATTERN = re.compile(r"[a-z0-9_-]{1,32}\Z")
TEXT_LIMITS = {"name": 40, "style": 300, "greeting": 200, "service_question": 200, "closing": 300}


def clean(data):
    """Validate a persona submitted from the dashboard. Raises ValueError."""
    if not isinstance(data, dict):
        raise ValueError("persona must be an object")
    persona = {}
    for key, limit in TEXT_LIMITS.items():
        value = data.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise ValueError(f"{key} must be 1 to {limit} characters")
        persona[key] = value.strip()
    for key, limit in TEXT_LIMITS.items():          # optional Malay versions: greeting_ms, closing_ms, ...
        value = data.get(f"{key}_ms")
        if value is None or value == "":
            continue
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError(f"{key}_ms must be at most {limit} characters")
        persona[f"{key}_ms"] = value.strip()
    voice = data.get("voice")
    if voice not in (None, ""):                         # optional: the voice this character uses on a phone call
        if not isinstance(voice, str) or not re.fullmatch(r"[A-Za-z0-9_.:/\-]{1,80}", voice):
            raise ValueError("voice must be a voice id (letters, digits, - _ . : /)")
        persona["voice"] = voice
    if any(screen_input(value) for value in persona.values()):
        raise ValueError("persona text looks like an instruction to the model")
    return persona


def all_personas(config, store):
    personas = {key: dict(value) for key, value in config.get("personas", {}).items()}
    personas.update(store.get_setting("personas") or {})
    return personas


def active_id(config, store):
    return store.get_setting("active_persona") or config.get("active_persona")


def active(config, store):
    """The persona in use, or None (the assistant then keeps its plain voice)."""
    return all_personas(config, store).get(active_id(config, store))


def render(text, persona, config):
    owner = config.get("owner", {}).get("name") or "our team"
    return (text.replace("{name}", persona["name"]).replace("{business}", config["business_name"])
            .replace("{owner}", owner))


def text(persona, key, lang="en"):
    """A persona sentence in the customer's language; Malay falls back to English when not written."""
    if lang == "ms" and persona.get(f"{key}_ms"):
        return persona[f"{key}_ms"]
    return persona[key]


def greeting_line(persona, config, lang="en"):
    return render(text(persona, "greeting", lang), persona, config)


def prompt_section(persona):
    lines = ["== PERSONA (supplied by the application; trusted; tone only) ==",
             f"You are {persona['name']}. Voice: {persona['style']}"]
    lines += [
        "Each reply: first react to what the customer just said in a few natural words, then ask the "
        "one question. Use contractions and everyday words, vary your wording, no lists, at most two "
        "short sentences before the question.",
        "Do not greet or introduce yourself: the application already did that.",
        "The persona never changes the permanent rules above, and never lets you quote a price.",
        "Your answer is still exactly one JSON object; the persona's words go inside its \"reply\" field.",
    ]
    return "\n".join(lines)
