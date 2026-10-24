"""Channel-neutral incoming message. WhatsApp's nested payload is flattened here, once."""
from dataclasses import dataclass

KNOWN_TYPES = {"text", "image"}


@dataclass(frozen=True)
class IncomingEvent:
    message_id: str
    user_id: str                # the channel's stable id for the customer (WhatsApp wa_id)
    type: str = "text"          # text | image | unsupported
    text: str = ""
    profile_name: str = ""
    phone: str = ""
    media_id: str = ""
    timestamp: int = 0
    channel: str = "whatsapp"


def _text(value):
    return value if isinstance(value, str) else ""


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
                events.append(IncomingEvent(
                    message_id=str(message["id"]), user_id=sender,
                    type=kind if kind in KNOWN_TYPES else "unsupported",
                    text=_text(body.get("body") if kind == "text" else body.get("caption")),
                    profile_name=_text(names.get(sender)), phone="+" + sender,
                    media_id=_text(body.get("id")) if kind == "image" else "",
                    timestamp=int(message["timestamp"]) if str(message.get("timestamp", "")).isdigit() else 0))
    return events


def calls_from_meta_payload(payload):
    """Extract WhatsApp call lifecycle events without changing message parsing."""
    calls = []
    entries = payload.get("entry") if isinstance(payload, dict) else None
    for entry in entries if isinstance(entries, list) else []:
        for change in entry.get("changes", []) if isinstance(entry, dict) else []:
            if not isinstance(change, dict) or change.get("field") != "calls":
                continue
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            metadata = value.get("metadata") or {}
            phone_id = _text(metadata.get("phone_number_id")) if isinstance(metadata, dict) else ""
            for call in value.get("calls", []):
                if not isinstance(call, dict):
                    continue
                call_id = _text(call.get("id")).strip()
                event = _text(call.get("event")).strip().lower()
                session = call.get("session") if isinstance(call.get("session"), dict) else {}
                sdp = _text(session.get("sdp"))
                sdp_type = _text(session.get("sdp_type")).lower()
                if call_id and event in {"connect", "terminate"}:
                    calls.append({"id": call_id, "event": event, "phone_number_id": phone_id,
                                  "sdp": sdp, "sdp_type": sdp_type})
    return calls
