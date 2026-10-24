"""Deterministic conversation steps around the model: service check, owner introduction,
wrap-up recap and confirmation, side questions, corrections, the waiting period and repeat orders.
No model is involved, so none of this text can drift. Every sentence comes from i18n (English or Malay)."""
import re
import time

from . import contact
from .i18n import ISSUE_MS, t
from .persona import text as persona_text
from .schema import single_wall

_SUPPORTED = re.compile(
    r"\b(paint\w*|repaint\w*|walls?|ceilings?|rooms?|bedrooms?|living|kitchen|bathrooms?|hall|"
    r"house|home|apartment|condo|flat|office|quot\w*|cat|mengecat\w*|dinding|siling|bilik|rumah|kondo|"
    r"pangsapuri|pejabat|dapur|tandas|ruang tamu|sebut ?harga)\b", re.I)
_UNSUPPORTED = re.compile(
    r"\b(exterior|outside|outdoors?|roofs?|fences?|gates?|garage|deck|pool|floors?|furniture|"
    r"cars?|vehicles?|luar|bumbung|pagar|garaj|lantai|perabot|kereta|kolam|kenderaan)\b", re.I)
_INTERIOR = re.compile(r"\b(interior|inside|indoors?|dalam|dalaman)\b", re.I)
_NO_WORDS = contact.NEGATIVE | {"not", "dont", "don't", "jangan"}


def check_service(message):
    """supported | unsupported | unknown (greeting or a question with no job in it)."""
    if _UNSUPPORTED.search(message) and not _INTERIOR.search(message):
        return "unsupported"
    return "supported" if _SUPPORTED.search(message) else "unknown"


def _owner_for(config, lang):
    return (config.get("owner") or {}).get("name") or ("pasukan kami" if lang == "ms" else "our team")


def decline_reply(state, config):
    return t("decline", state.lang, services=" and ".join(config["services"]))


def is_yes(message):
    words = contact._words(message)
    return (0 < len(words) <= 5 and not any(w in _NO_WORDS for w in words)
            and any(w in contact.AFFIRMATIVE for w in words) and not re.search(r"\d", message))


def contact_intro(state):
    return t("contact_intro", state.lang) + contact.begin(state)


def owner_line(config, lang="en"):
    owner = config.get("owner") or {}
    if not owner.get("name"):
        return ""
    title = owner.get("title", "owner")
    if lang == "ms" and title == "owner":
        title = "pemilik"
    return t("owner_line", lang, owner=owner["name"], title=title)


_SURFACE_MS = {"one wall": "satu dinding", "walls": "dinding", "wall": "dinding", "ceiling": "siling"}


def _approx(state):
    return t("recap_estimate", state.lang) if state.estimated else ""


def recap(state):
    v, lang, parts = state.verified, state.lang, []
    for key, label in (("address", "recap_address"), ("property_type", "recap_property")):
        if v.get(key):
            parts.append(f"{t(label, lang)}: {v[key]}")
    if v.get("surfaces"):
        shown = [(_SURFACE_MS.get(str(s).lower(), s) if lang == "ms" else s) for s in v["surfaces"]]
        parts.append(f"{t('recap_surfaces', lang)}: " + ", ".join(shown))
    dims = [v.get(k) for k in ("room_length_m", "room_width_m", "room_height_m")]
    if single_wall(v.get("surfaces")) and dims[0] is not None and dims[2] is not None:
        parts.append(t("recap_wall", lang, l=dims[0], h=dims[2]) + _approx(state))
    elif all(d is not None for d in dims):
        parts.append(t("recap_room", lang, l=dims[0], w=dims[1], h=dims[2]) + _approx(state))
    for key, label in (("surface_condition", "recap_condition"), ("paint_tier", "recap_paint"),
                       ("colour", "recap_colour"), ("preferred_datetime", "recap_time")):
        if v.get(key):
            parts.append(f"{t(label, lang)}: {v[key]}")
    return "\n".join("- " + p for p in parts)


def wrapup_reply(state, config):
    name, phone = contact.known_contact(state)
    head = t("wrap_head", state.lang, name=name, phone=phone, owner_line=owner_line(config, state.lang)).strip()
    return f"{head}\n\n{t('wrap_here', state.lang)}\n{recap(state)}\n\n{t('wrap_ok', state.lang)}"


def closing_reply(state, config):
    persona = config.get("persona")
    if persona:
        from .persona import render
        return render(persona_text(persona, "closing", state.lang), persona, config)
    return t("closing", state.lang)


_DATE_WORDS = re.compile(
    r"\b(mon|tue|wed|thu|fri|sat|sun)[a-z]*\b|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b|"
    r"\b(today|tomorrow|tonight|weekend|weekday|morning|afternoon|evening|next week|next month)\b|"
    r"\b(isnin|selasa|rabu|khamis|jumaat|sabtu|ahad|esok|lusa|petang|malam|pagi|minggu depan|bulan depan|"
    r"hari ini|hujung minggu|januari|februari|mac|april|mei|jun|julai|ogos|september|oktober|november|"
    r"disember)\b|"
    r"\b\d{1,2}\s?(am|pm)\b|\b\d{1,2}[/.-]\d{1,2}\b", re.I)
_DATE_QUESTION = re.compile(
    r"\b(date|when|schedule|time|available|availability|come over|come by|book|tarikh|bila|jadual|masa|"
    r"datang|tempah|kosong)\b", re.I)
_ASAP = re.compile(
    r"\b(asap|as soon as poss\w*|any ?time|whenever|flexible|no preference|any day|soonest|secepat mungkin|"
    r"bila-?bila|fleksibel|terpulang|secepatnya|apa-?apa masa)\b", re.I)
_BARE_NO = re.compile(
    r"^\s*(no|nope|nah|none|nothing|not really|no issues?|no damage|no specific|tak|tidak|tiada|"
    r"tak ada|tiada masalah|tiada kerosakan|tak de|xde)[.! ]*$", re.I)
NO_PREFERENCE = re.compile(
    r"\b(no preference|any|anything|you choose|your choice|up to you|not sure|dont mind|don'?t mind|whatever|"
    r"recommend\w*|surprise me|no idea|idk|you decide|terpulang|apa saja|apa-?apa|mana-?mana|tak kisah|"
    r"tiada pilihan|awak pilih|cadangkan|tak pasti|tidak pasti)\b", re.I)


def when_in(message):
    """The customer's answer to "when would you like us to come": a date or time, or flexible."""
    if _DATE_WORDS.search(message) or _ASAP.search(message):
        return message.strip()[:120]
    if _BARE_NO.match(message):
        return "flexible, no specific date"
    return None


_QUESTION_START = re.compile(
    r"^\s*(do|does|can|could|what|whats|what's|how|which|is|are|will|would|any|apa|berapa|bila|boleh|adakah|"
    r"macam mana|bagaimana|siapa|di mana|kenapa)\b", re.I)
_FAQ_SERVICES = re.compile(
    r"\b(services?|offer|other|else|what (do|can) you|perkhidmatan|tawar\w*|lain|apa lagi)\b", re.I)
_FAQ_PRICE = re.compile(
    r"\b(price|prices|cost|costs|how much|expensive|cheap|charge|rates?|harga|kos|berapa|mahal|murah|bayar)\b",
    re.I)
_FAQ_PAINT = re.compile(
    r"\b(paints?|colou?rs?|brands?|quality|finish|cat|warna|jenama|kualiti)\b", re.I)


def faq_answer(message, config, stage="job", lang="en"):
    """A fixed answer to a side question (services, price, paint), or None. Nothing here is invented:
    it only repeats the business's own configuration. While collecting the job only services and
    price are answered here, because the paint questions are part of the job itself."""
    if "?" not in message and not _QUESTION_START.match(message):
        return None
    owner = _owner_for(config, lang)
    if _FAQ_PRICE.search(message):
        return t("faq_price", lang, owner=owner)
    if _FAQ_SERVICES.search(message):
        return t("faq_services", lang, services=", ".join(config["services"]))
    if stage != "job" and _FAQ_PAINT.search(message):
        tiers = list((config.get("pricing") or {}).get("paint_tiers", {})) or ["standard"]
        joiner = " atau " if lang == "ms" else " or "
        names = ", ".join(tiers[:-1]) + joiner + tiers[-1] if len(tiers) > 1 else tiers[0]
        return t("faq_paint", lang, tiers=names, owner=owner)
    return None


# --- changing their mind ------------------------------------------------------------------------
CORRECTION = re.compile(
    r"\b(nvm|nevermind|never mind|actually|sorry|my bad|i mean|correction|wait|no it'?s|not \d|make it|"
    r"change (it )?to|instead|rather|wrong|mistake|oops|silap|salah|maaf|bukan|sebenarnya|tukar|ubah|"
    r"maksud saya|eh|lupa|tak jadi)\b", re.I)


def is_correction(message):
    return bool(CORRECTION.search(message))


# --- repeat customers ---------------------------------------------------------------------------
_AGAIN = re.compile(
    r"\b(another|new|also|one more|again|different|other|next|second|lagi|baru|lain|satu lagi|juga|pula)\b", re.I)
_WANT = re.compile(r"\b(want|need|like|looking|planning|nak|mahu|hendak|perlu|ingin)\b", re.I)


def new_job_intent(message, state):
    """A customer who already finished a job asks for another one."""
    if not (_SUPPORTED.search(message) and _WANT.search(message)):
        return False
    return bool(_AGAIN.search(message)) or state.quote_status in ("approved", "final")


def start_new_order(state):
    """Archive the finished job and reset the job fields; the customer's name, phone and language stay."""
    state.orders.append({
        "verified": dict(state.verified), "quote": state.quote, "quote_status": state.quote_status,
        "photo_assessment": state.photo_assessment, "estimated": list(state.estimated),
        "followups": list(state.followups), "created_at": state.created_at, "closed_at": time.time()})
    state.verified = {k: v for k, v in state.verified.items() if k in ("customer_name", "phone")}
    state.stage, state.quote, state.quote_status, state.photo_assessment = "job", None, "", None
    state.estimated, state.followups, state.waiting_count, state.attention = [], [], 0, False
    state.pending_conflict, state.history, state.last_field = None, [], ""
    state.needs_human, state.created_at = False, time.time()
    state.greeted = state.service_checked = state.contact_confirmed = True


# --- after the chat: waiting for the SME ----------------------------------------------------------
_IMPORTANT = re.compile(
    r"\b(cancel|urgent|emergency|change|wrong|mistake|incorrect|problem|complain\w*|refund|call me|phone me|"
    r"whatsapp me|address|moved|asap|batal|segera|tukar|salah|silap|masalah|hubungi|telefon saya|alamat|"
    r"kecemasan|tak jadi)\b", re.I)
_MEASURE = re.compile(r"\d\s*(m|metres?|meters?|ft|feet|kaki|cm)\b", re.I)
WAIT_REPLIES = 2          # short replies while waiting, then silence unless the message matters


def important(message):
    return bool(_IMPORTANT.search(message) or _MEASURE.search(message) or is_correction(message))


def after_done(state, message, config):
    """The reply once the chat is complete, or None to stay silent. While the SME has not confirmed, the
    bot answers real questions and anything important (and flags it), acknowledges a couple of other
    messages, then stops replying so the customer is not answered in circles."""
    lang, owner = state.lang, _owner_for(config, state.lang)
    waiting = state.quote_status in ("", "pending_approval", "needs_inspection")
    if len(state.followups) < 50:
        state.followups.append({"text": message[:300], "at": time.time()})
    faq = faq_answer(message, config, "done", lang)
    if _DATE_WORDS.search(message):
        state.verified["preferred_datetime"] = message.strip()[:120]
        state.attention = True
        return t("date_noted", lang, when=state.verified["preferred_datetime"], owner=owner)
    if faq:
        return faq
    if _DATE_QUESTION.search(message):
        known = state.verified.get("preferred_datetime")
        have = t("date_have", lang, when=known) if known else ""
        return t("date_ask", lang, have=have, owner=owner)
    if important(message):
        state.attention = True
        return t("important", lang, owner=owner)
    if waiting:
        if state.waiting_count >= WAIT_REPLIES:
            return None
        state.waiting_count += 1
    return t(f"after_{len(state.history) // 2 % 4 + 1}", lang, owner=owner)
