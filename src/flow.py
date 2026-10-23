"""Deterministic conversation steps around the model: service check, owner introduction,
wrap-up recap and confirmation. No model is involved, so none of this text can drift."""
import re

from . import contact
from .persona import render

_SUPPORTED = re.compile(
    r"\b(paint\w*|repaint\w*|walls?|ceilings?|rooms?|bedrooms?|living|kitchen|bathrooms?|hall|"
    r"house|home|apartment|condo|flat|office|quot\w*)\b", re.I)
_UNSUPPORTED = re.compile(
    r"\b(exterior|outside|outdoors?|roofs?|fences?|gates?|garage|deck|pool|floors?|furniture|"
    r"cars?|vehicles?)\b", re.I)
_INTERIOR = re.compile(r"\b(interior|inside|indoors?)\b", re.I)
_NO_WORDS = contact.NEGATIVE | {"not", "dont", "don't"}


def check_service(message):
    """supported | unsupported | unknown (greeting or a question with no job in it)."""
    if _UNSUPPORTED.search(message) and not _INTERIOR.search(message):
        return "unsupported"
    return "supported" if _SUPPORTED.search(message) else "unknown"


def decline_reply(config):
    services = " and ".join(s.replace("interior ", "") for s in config["services"])
    return (f"Thanks for asking! We only do interior {services} at the moment, so I'll pass this "
            "to the team in case they can help.")


def is_yes(message):
    words = contact._words(message)
    return (0 < len(words) <= 5 and not any(w in _NO_WORDS for w in words)
            and any(w in contact.AFFIRMATIVE for w in words) and not re.search(r"\d", message))


def contact_intro(state):
    return "That's everything I need about the job, thank you! " + contact.begin(state)


def owner_line(config):
    owner = config.get("owner") or {}
    if not owner.get("name"):
        return ""
    return (f"{owner['name']}, our {owner.get('title', 'owner')}, will personally review your job "
            "and confirm your quotation.")


def recap(state):
    v, parts = state.verified, []
    for key, label in (("address", "Address"), ("property_type", "Property")):
        if v.get(key):
            parts.append(f"{label}: {v[key]}")
    if v.get("surfaces"):
        parts.append("Surfaces: " + ", ".join(v["surfaces"]))
    dims = [v.get(k) for k in ("room_length_m", "room_width_m", "room_height_m")]
    if all(d is not None for d in dims):
        parts.append("Room: {:g} m long, {:g} m wide, {:g} m high".format(*dims))
    for key, label in (("surface_condition", "Condition"), ("paint_tier", "Paint"),
                       ("colour", "Colour"), ("preferred_datetime", "Preferred time")):
        if v.get(key):
            parts.append(f"{label}: {v[key]}")
    return "\n".join("- " + p for p in parts)


def wrapup_reply(state, config):
    name, phone = contact.known_contact(state)
    text = f"Thank you, I've noted this under {name} ({phone}). {owner_line(config)}".strip()
    return f"{text}\n\nHere's what I have:\n{recap(state)}\n\nIs everything correct?"


def closing_reply(config):
    persona = config.get("persona")
    if persona:
        return render(persona["closing"], persona, config)
    return "Wonderful, thank you! Your quotation will come here once it's confirmed."
