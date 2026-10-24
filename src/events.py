"""Channel-neutral incoming message. WhatsApp's nested payload is flattened here, once."""
from dataclasses import dataclass

KNOWN_TYPES = {"text", "image", "audio"}


@dataclass(frozen=True)
class IncomingEvent:
    message_id: str
    user_id: str                # the channel's stable id for the customer (WhatsApp wa_id)
    type: str = "text"          # text | image | audio (a voice note) | unsupported
    text: str = ""
    profile_name: str = ""
    phone: str = ""
    media_id: str = ""
    timestamp: int = 0
    channel: str = "whatsapp"


def _text(value):
    return value if isinstance(value, str) else ""


def _location_text(body):
    """A shared WhatsApp location as text, so it can answer "what is the address?"."""
    label = " ".join(x for x in (_text(body.get("name")), _text(body.get("address"))) if x)
    try:
        coords = f"{float(body['latitude']):.5f}, {float(body['longitude']):.5f}"
    except (KeyError, TypeError, ValueError):
        coords = ""
    return f"{label} (location {coords})".strip() if coords else label


def from_flat(data):
    """The flat JSON that n8n (or any other front door) posts. Raises ValueError if unusable."""
    if not isinstance(data, dict):
        raise ValueError("event must be a JSON object")
    message_id, user_id = _text(data.get("message_id")).strip(), _text(data.get("user_id")).strip()
    if not message_id or not user_id:
        raise ValueError("message_id and user_id are required")
    kind = _text(data.get("type")) or "text"
    try:
        timestamp = int(data.get("timestamp") or 0)
    except (TypeError, ValueError):
        timestamp = 0
    return IncomingEvent(
        message_id=message_id, user_id=user_id, type=kind if kind in KNOWN_TYPES else "unsupported",
        text=_text(data.get("text")), profile_name=_text(data.get("profile_name")),
        phone=_text(data.get("phone")), media_id=_text(data.get("media_id")), timestamp=timestamp,
        channel=_text(data.get("channel")) or "whatsapp")


def from_meta_payload(payload):
    """Meta Cloud API webhook body -> list of events. Delivery receipts (statuses) are ignored."""
    events = []
    entries = payload.get("entry") if isinstance(payload, dict) else None
    for entry in entries if isinstance(entries, list) else []:
        for change in entry.get("changes", []) if isinstance(entry, dict) else []:
            value = change.get("value") if isinstance(change, dict) else None
            if not isinstance(value, dict):
                continue
            names = {c.get("wa_id"): (c.get("profile") or {}).get("name", "")
                     for c in value.get("contacts", []) if isinstance(c, dict)}
            for message in value.get("messages", []):
                if not isinstance(message, dict) or not message.get("id") or not message.get("from"):
                    continue
                kind = message.get("type")
                body = message.get(kind) if isinstance(message.get(kind), dict) else {}
                sender = str(message["from"])
                if kind == "location" and _location_text(body):
                    kind, body = "text", {"body": _location_text(body)}
                events.append(IncomingEvent(
                    message_id=str(message["id"]), user_id=sender,
                    type=kind if kind in KNOWN_TYPES else "unsupported",
                    text=_text(body.get("body") if kind == "text" else body.get("caption")),
                    profile_name=_text(names.get(sender)), phone="+" + sender,
                    media_id=_text(body.get("id")) if kind in ("image", "audio") else "",
                    timestamp=int(message["timestamp"]) if str(message.get("timestamp", "")).isdigit() else 0))
    return events
