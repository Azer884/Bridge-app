"""The dashboard's view of a customer's job: the shapes the frontend's shared/types.ts expects, built from the
conversation state, the stored messages, bookings and audit log. Pure functions, no HTTP."""
import time
from datetime import datetime

from .calendar_scheduler import TZ
from .schema import single_wall

CONDITION_UI = {"good": "good", "minor": "fair", "moderate": "poor", "severe": "poor"}      # engine -> form
CONDITION_ENGINE = {"good": "good", "fair": "minor", "poor": "moderate"}                    # form -> engine
DIMENSIONS = {"length_m": "room_length_m", "width_m": "room_width_m", "height_m": "room_height_m"}


def front_status(state):
    """The frontend's QuoteStatus for a conversation."""
    if state.quote_status == "final":
        return "completed"
    if state.stage != "done" or not state.quote_status:
        return "collecting"
    return state.quote_status


def stage_of(state, booked):
    """Pipeline stage: pending_extraction | requires_approval | quote_sent | scheduled | completed."""
    status = front_status(state)
    if status == "collecting":
        return "pending_extraction"
    if status == "completed":
        return "completed"
    if status == "approved":
        return "scheduled" if booked else "quote_sent"
    return "requires_approval"


def customer_name(state):
    return state.verified.get("customer_name") or state.channel.get("name") or state.channel.get("phone") or state.conversation_id


def job_view(state):
    v = state.verified
    return {"address": v.get("address"), "surfaces": ", ".join(v.get("surfaces") or []) or None,
            "room_length_m": v.get("room_length_m"), "room_width_m": v.get("room_width_m"),
            "room_height_m": v.get("room_height_m"), "surface_condition": v.get("surface_condition"),
            "preferred_datetime": v.get("preferred_datetime"), "paint_tier": v.get("paint_tier"),
            "colour": v.get("colour"), "name": customer_name(state),
            "phone": v.get("phone") or state.channel.get("phone"), "location": location_view(v.get("location"))}


def maps_url(lat, lon):
    return f"https://www.google.com/maps?q={lat},{lon}"


def location_view(location):
    """A shared location with a link that opens it in Google Maps, or None."""
    if not location or location.get("lat") is None:
        return None
    return {**location, "maps_url": maps_url(location["lat"], location["lon"])}


def quote_view(quote, state=None):
    """The draft with the engine's labour hours on it. The approved or final total rides along."""
    if not quote:
        return None
    out = dict(quote)
    out["labor_hours"] = (quote.get("schedule") or {}).get("total_labour_hours")
    for key in ("approved_total", "final_total"):
        if key in quote:
            out[key] = quote[key]
    return out


def quote_item(state, booked=False):
    return {"user_id": state.conversation_id, "status": front_status(state), "customer": customer_name(state),
            "phone": state.verified.get("phone") or state.channel.get("phone"), "job": job_view(state),
            "quote": quote_view(state.quote), "stage": stage_of(state, booked), "lang": state.lang,
            "is_estimate": True, "estimated_fields": state.estimated, "attention": state.attention,
            "needs_human": state.needs_human, "human_active": state.human_until > time.time(),
            "followups": state.followups, "updated_at": datetime.fromtimestamp(state.created_at, TZ).isoformat()
            if state.created_at else None}


# --- the editable parameters -----------------------------------------------------------------------
def param_schema(state):
    fields = [
        {"key": "length_m", "label": "Length" if single_wall(state.verified.get("surfaces")) else "Room length",
         "type": "number", "unit": "m", "min": 0.5, "max": 30, "step": 0.1},
    ]
    if not single_wall(state.verified.get("surfaces")):
        fields.append({"key": "width_m", "label": "Room width", "type": "number", "unit": "m", "min": 0.5,
                       "max": 30, "step": 0.1})
    fields += [
        {"key": "height_m", "label": "Height", "type": "number", "unit": "m", "min": 1.8, "max": 8, "step": 0.1},
        {"key": "surface_condition", "label": "Surface condition", "type": "select", "options": [
            {"value": "good", "label": "Good"}, {"value": "fair", "label": "Fair, small repairs"},
            {"value": "poor", "label": "Poor, heavy prep"}]},
        {"key": "coats", "label": "Coats", "type": "number", "min": 1, "max": 4, "step": 1, "integer": True},
        {"key": "tier", "label": "Paint tier", "type": "select", "options": [
            {"value": "economy", "label": "Economy"}, {"value": "standard", "label": "Standard"},
            {"value": "premium", "label": "Premium"}]},
    ]
    return fields


def ai_values(state):
    """What the assistant read from the chat, in the form's keys. Never changes after the chat."""
    inputs = (state.quote or {}).get("inputs") or {}
    v = state.verified
    values = {"length_m": v.get("room_length_m"), "width_m": v.get("room_width_m"), "height_m": v.get("room_height_m"),
              "surface_condition": CONDITION_UI.get(inputs.get("condition_level"), "good"),
              "coats": inputs.get("coats", 2), "tier": inputs.get("paint_tier", "standard")}
    if single_wall(v.get("surfaces")):
        values.pop("width_m")
    return values


def params_view(state):
    ai = ai_values(state)
    current = {**ai, **{k: v for k, v in state.overrides.items() if k in ai}}
    confidence = {"length_m": 0.65 if "room_length_m" in state.estimated else 0.95,
                  "width_m": 0.65 if "room_width_m" in state.estimated else 0.95,
                  "height_m": 0.65 if "room_height_m" in state.estimated else 0.95,
                  "surface_condition": 0.6 if state.photo_assessment else 0.9, "coats": 1.0,
                  "tier": 0.9 if state.verified.get("paint_tier") in ("economy", "standard", "premium") else 0.5}
    return {"kind": "painting", "schema": param_schema(state), "ai": ai, "current": current,
            "confidence": {k: v for k, v in confidence.items() if k in ai}}


def engine_inputs(state, params=None):
    """(verified fields, engine overrides) for the pricing engine: the chat's answers with the owner's form
    values applied on top. `params` defaults to the saved overrides."""
    params = state.overrides if params is None else params
    verified = dict(state.verified)
    for key, field in DIMENSIONS.items():
        if params.get(key) is not None:
            verified[field] = float(params[key])
    overrides = {}
    if params.get("surface_condition") in CONDITION_ENGINE:
        overrides["condition_level"] = CONDITION_ENGINE[params["surface_condition"]]
    if params.get("coats"):
        overrides["coats"] = int(params["coats"])
    if params.get("tier"):
        overrides["tier"] = params["tier"]
    return verified, overrides


def changed_params(state, params):
    """The form values that differ from what the assistant read, as {key: value}."""
    ai = ai_values(state)
    return {k: v for k, v in params.items() if k in ai and v != ai[k]}


# --- chat, photos, audit ----------------------------------------------------------------------------
def _iso(ts):
    return datetime.fromtimestamp(ts, TZ).isoformat()


def chat_view(messages):
    chat = []
    for m in messages:
        if m["text"] == "[voice note]":
            continue
        role = {"in": "customer", "owner": "owner"}.get(m["direction"], "assistant")
        chat.append({"id": str(m["id"]), "role": role,
                     "text": m["text"] or ("[photo]" if m["media_id"] else ""), "ts": _iso(m["ts"]),
                     **({"photo_ids": [m["media_id"]]} if m["media_id"] and m["direction"] == "in" else {})})
    return chat


def photos_view(messages):
    return [{"id": m["media_id"], "url": f"/api/media/{m['media_id']}", "caption": m["text"] or "Customer photo",
             "ts": _iso(m["ts"])} for m in messages if m["media_id"] and m["direction"] == "in"
            and m["text"] != "[voice note]"]


def audit_view(entries):
    return [{**e, "ts": _iso(e["ts"])} for e in sorted(entries, key=lambda e: e["seq"])]


def booking_view(booking, state=None):
    out = {k: booking[k] for k in ("id", "user_id", "customer", "phone", "address", "start", "end")}
    out["status"] = booking["status"]
    out["quote_status"] = front_status(state) if state and state.quote else "none"
    out["quote_total"] = ((state.quote or {}).get("approved_total") or (state.quote or {}).get("total")) if state else None
    return out


def detail_view(state, messages, audit, booked):
    item = quote_item(state, booked)
    schedule = (state.quote or {}).get("schedule") or {}
    return {**item, "params": params_view(state) if state.quote else None, "chat": chat_view(messages),
            "photos": photos_view(messages), "audit": audit_view(audit),
            "duration_hours": schedule.get("hours_on_site"),
            "locked": state.quote_status in ("approved", "final")}
