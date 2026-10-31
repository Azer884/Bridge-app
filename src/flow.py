"""Deterministic conversation steps around the model: service check, owner introduction,
wrap-up recap and confirmation, side questions, corrections, the waiting period and repeat orders.
No model is involved, so none of this text can drift. Every sentence comes from i18n (English or Malay)."""
import re
import time

from . import contact
from .i18n import ISSUE_MS, t
from .persona import text as persona_text
from .rooms import all_rooms
from .schema import single_wall

_SUPPORTED = re.compile(
    r"\b(paint\w*|repaint\w*|walls?|ceilings?|rooms?|bedrooms?|living|kitchen|bathrooms?|hall|"
    r"house|home|apartment|condo|flat|office|quot\w*|cat|mengecat\w*|dinding|siling|bilik|rumah|kondo|"
    r"pangsapuri|pejabat|dapur|tandas|ruang tamu|sebut ?harga)\b", re.I)
_UNSUPPORTED = re.compile(
    r"\b(exterior|outside|outdoors?|roofs?|fences?|gates?|garage|deck|pool|floors?|furniture|"
    r"cars?(?! park)|vehicles?|cabinets?|cupboards?|wardrobes?|luar|bumbung|pagar|garaj|lantai|perabot|kereta|kolam|"
    r"kenderaan|almari)\b", re.I)
_PREP = re.compile(r"\b(move (my |the )?furniture|furniture (out|away)|cover(ing)? (the )?(floor|furniture)|not at home)\b", re.I)
# other trades: declined unless the message is plainly about painting a wall or ceiling
_OTHER_TRADE = re.compile(r"\b(plumb\w*|electric\w*|wallpaper(?:s|ing)?|tiles?|tiling|carpent\w*|aircond\w*|"
                          r"pest control|cleaning|paip|elektrik|jubin)\b", re.I)
_ROOM_PAINT = re.compile(r"\b(walls?|ceilings?|dinding|siling)\b", re.I)
_INTERIOR = re.compile(r"\b(interior|inside|indoors?|dalam|dalaman)\b", re.I)
_NO_WORDS = contact.NEGATIVE | {"not", "dont", "don't", "jangan"}


def check_service(message):
    """supported | unsupported | unknown (greeting or a question with no job in it)."""
    if _PREP.search(message):
        return "unknown"
    if _UNSUPPORTED.search(message) and not _INTERIOR.search(message):
        return "unsupported"
    if _OTHER_TRADE.search(message) and not _ROOM_PAINT.search(message) and not re.search(r"\bpaint\w*|\bcat\b", message, re.I):
        return "unsupported"
    return "supported" if _SUPPORTED.search(message) else "unknown"


def _owner_for(config, lang):
    return (config.get("owner") or {}).get("name") or ("pasukan kami" if lang == "ms" else "our team")


_HUMAN = re.compile(
    r"\b(live agent|(?:a |an |real |actual )human\b(?!-)|real person|(speak|talk|chat) (to|with) (a |an |the |your )?(person|someone|somebody|agent|"
    r"owner|manager|human|representative|staff)|customer service|representative|operator|call me|ring me|"
    r"cakap dengan (orang|pemilik|manager|staf)|orang sebenar|nak cakap dengan)\b", re.I)


def wants_human(message):
    """The customer asks for a person: that is the owner's cue, not something to answer with another question."""
    return bool(_HUMAN.search(message))


_COLOUR_SUGGEST = re.compile(
    r"\b(suggest|recommend|advise|pick|choose|decide|match|cadang\w*|syorkan|pilihkan)\b.{0,50}\b(colou?rs?|warna)\b|"
    r"\b(what|which|any)\b.{0,20}\b(colou?rs?|warna)\b.{0,40}\b(suit|match|go with|fit|best|sesuai|cantik|photo|picture|pic|image|gambar)\b|"
    r"\b(colou?rs?|warna)\b.{0,30}\b(based on|from|according to|dari|berdasarkan)\b.{0,20}\b(photo|picture|pic|image|gambar)\b", re.I)


def wants_colour_suggestion(message):
    """"Suggest a colour based on the picture": the customer wants the colour chosen from their photo."""
    return bool(_COLOUR_SUGGEST.search(message))


def is_foreign_script(message):
    """Mostly letters of another alphabet (Arabic, Cyrillic, Chinese...), which the assistant cannot read."""
    letters = [c for c in message if c.isalpha()]
    if len(letters) < 4:
        return False
    return sum(1 for c in letters if ord(c) > 0x024F) / len(letters) > 0.5


def decline_reply(state, config):
    return t("decline", state.lang, services=" and ".join(config["services"]))


def is_yes(message):
    words = contact._words(message)
    return (0 < len(words) <= 5 and not any(w in _NO_WORDS for w in words)
            and any(w in contact.AFFIRMATIVE for w in words) and not re.search(r"\d", message)
            and not _SUPPORTED.search(message))


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
    for number, (name, length, width, height) in enumerate(all_rooms(v)[1:], start=2):
        label = f" ({name})" if name else ""
        if single_wall(v.get("surfaces")) or width is None:
            parts.append(t("recap_wall_n", lang, n=number, name=label, l=length or 0, h=height or 0))
        else:
            parts.append(t("recap_room_n", lang, n=number, name=label, l=length or 0, w=width, h=height or 0))
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
        return render(persona_text(persona, "closing", state.lang), persona, config, state.lang)
    return t("closing", state.lang)


_DATE_WORDS = re.compile(
    r"\b(monday|mon|tuesday|tues|tue|wednesday|wed|thursday|thurs|thur|thu|friday|fri|saturday|sat|sunday|sun)\b|"
    r"\b\d{1,2}(st|nd|rd|th)?\s+(january|jan|february|feb|march|mar|april|apr|may|june|jun|july|jul|august|aug|"
    r"september|sept|sep|october|oct|november|nov|december|dec)\b|"
    r"\b(january|jan|february|feb|march|mar|april|apr|may|june|jun|july|jul|august|aug|september|sept|sep|"
    r"october|oct|november|nov|december|dec)\s+\d{1,2}\b|"
    r"\b(today|tomorrow|tonight|weekend|weekday|morning|afternoon|evening|next week|next month)\b|"
    r"\b(isnin|selasa|rabu|khamis|jumaat|sabtu|ahad|esok|lusa|petang|malam|pagi|minggu depan|bulan depan|"
    r"hari ini|hujung minggu)\b|"
    r"\b\d{1,2}(st|nd|rd|th)?\s+(januari|februari|mac|april|mei|jun|julai|ogos|september|oktober|november|"
    r"disember)\b|"
    r"\b(lunch ?time|noon|midday|day after( tomorrow)?|next (mon|tues|wednes|thurs|fri|satur|sun)day|"
    r"in \d+ (days?|weeks?)|\d+ (days?|weeks?) (later|from now)|tengah ?hari|minggu ini)\b|"
    r"\b\d{1,2}\s?(am|pm)\b|\b\d{1,2}:\d{2}\b|\b\d{1,2}[/-]\d{1,2}\b", re.I)
_DATE_FILLER = {"make", "it", "sorry", "actually", "wait", "nvm", "no", "ok", "okay", "change", "to", "on", "at", "la", "lah", "pls", "please", "then"}
_NEGATED_DATE = re.compile(r"\b(except|not|bukan|kecuali|other than|besides|excluding|apart from)\b", re.I)
_GOOD_GREETING = re.compile(r"\b(good|selamat)\s+(morning|afternoon|evening|night|pagi|petang|malam|tengah ?hari)\b", re.I)
_PAST_DATE = re.compile(r"\b(yesterday|last (week|month|night)|semalam)\b", re.I)
_DATE_NEEDS_DAY = re.compile(r"\bafter (raya|ramadan|cny|chinese new year|deepavali|christmas|the holidays?)\b", re.I)
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
    r"\b(no preference|any|anything|you choose|you pick|you select|your pick|your choice|up to you|not sure|dont mind|don'?t mind|whatever|"
    r"recommend\w*|surprise me|no idea|idk|you decide|terpulang|apa saja|apa-?apa|mana-?mana|tak kisah|"
    r"tiada pilihan|awak pilih|cadangkan|tak pasti|tidak pasti)\b", re.I)


def when_in(message, strict=False):
    """The customer's answer to "when would you like us to come": a date or time, or flexible. In a long message
    that says other things too, only the part about the time is kept. `strict` (a time said unprompted) only
    accepts real dates, times and "anytime", not "no preference" or "I don't know"."""
    message = _GOOD_GREETING.sub(" ", message)              # "good morning" is a hello, not a time
    spans = sorted(m.span() for pattern in (_DATE_WORDS, _ASAP_TIME if strict else _ASAP) for m in pattern.finditer(message))
    if spans:
        words = message.split()
        if len(words) <= 3:
            kept = [w for w in words if w.lower().strip(",.!") not in _DATE_FILLER]
            return " ".join(kept or words)[:120]
        if _NEGATED_DATE.search(message):                   # "any day except Monday": keep what they said
            return " ".join(message.split())[:120]
        cluster = [spans[0]]
        for span in spans[1:]:
            if span[0] - cluster[-1][1] <= 25:
                cluster.append(span)
            else:
                cluster = [span]                            # a long message: the last time mentioned is the answer
        return " ".join(message[min(s for s, _ in cluster):max(e for _, e in cluster)].split())[:120]
    if not strict and (_BARE_NO.match(message) or _NO_DATE_PREF.search(message) or _DONT_KNOW.search(message)):
        return "flexible, no specific date"
    return None


_NO_DATE_PREF = re.compile(
    r"\b(no preference|any|anything|you choose|you pick|you decide|your choice|up to you|dont mind|don'?t mind|whatever|"
    r"flexible|terpulang|apa saja|apa-?apa|mana-?mana|tak kisah)\b", re.I)


_MONTH_NUMBER = {"jan": 1, "feb": 2, "mar": 3, "mac": 3, "apr": 4, "may": 5, "mei": 5, "jun": 6, "jul": 7, "aug": 8,
                 "ogo": 8, "sep": 9, "oct": 10, "okt": 10, "nov": 11, "dec": 12, "dis": 12}
_MONTH_NAMES = ("january|jan|february|feb|march|mar|mac|april|apr|may|mei|june|jun|july|jul|august|aug|ogos|"
                "september|sept|sep|october|oct|okt|november|nov|december|disember|dec|dis")
_DAY_MONTH = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_NAMES})\b\.?(?:,?\s+(\d{{4}}))?", re.I)
_MONTH_DAY = re.compile(rf"\b({_MONTH_NAMES})\b\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(\d{{4}}))?", re.I)


def explicit_date(message):
    """(day, month, year or None) of the first "20 Oct", "Oct 20" or "20 October 2027" in the message, else None."""
    found = _DAY_MONTH.search(message)
    if found:
        return int(found.group(1)), _MONTH_NUMBER[found.group(2).lower()[:3]], int(found.group(3)) if found.group(3) else None
    found = _MONTH_DAY.search(message)
    if found:
        return int(found.group(2)), _MONTH_NUMBER[found.group(1).lower()[:3]], int(found.group(3)) if found.group(3) else None
    return None


def passed_this_year(message, today=None):
    """True for a day and month with no year that has already gone by this year ("20 Oct" said on 30 Oct). The
    customer must then give the year, so a typo or an old date is never booked silently."""
    from datetime import date as _date
    found = explicit_date(message)
    if not found or found[2] is not None:
        return False
    today = today or _date.today()
    try:
        return _date(today.year, found[1], found[0]) < today
    except ValueError:
        return False


_SUNDAY = re.compile(r"\b(sunday|sun|ahad)\b", re.I)
_SATURDAY = re.compile(r"\b(saturday|sabtu)\b", re.I)
_WEEKEND = re.compile(r"\b(weekends?|hujung minggu)\b", re.I)
_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
                 "ten": 10, "eleven": 11, "twelve": 12}
_CLOCK = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b|\b([01]?\d|2[0-3]):([0-5]\d)\b|"
                    rf"\b({'|'.join(_NUMBER_WORDS)})\s*(am|pm)\b", re.I)       # "3 am", "15:00", "three AM"
# Public holidays: named ones (their dates move every year) and the fixed-date federal ones as (month, day).
_HOLIDAY_NAMES = re.compile(
    r"(?<!after )(?<!before )(?<!selepas )(?<!sebelum )\b(hari raya|raya|aidilfitri|aidiladha|deepavali|diwali|"
    r"chinese new year|cny|christmas|thaipusam|wesak|vesak|merdeka|malaysia day|labou?r day|new year'?s? day|"
    r"awal muharram|maulidur rasul|nuzul quran|agong'?s? birthday|public holiday|cuti umum)\b", re.I)
_FIXED_HOLIDAYS = {(1, 1), (5, 1), (8, 31), (9, 16), (12, 25)}
_TOMORROW = re.compile(r"\b(tomorrow|esok)\b", re.I)
_TODAY = re.compile(r"\b(today|tonight|hari ini)\b", re.I)


def _closed_day(day, working_days):
    return day.weekday() not in working_days or (day.month, day.day) in _FIXED_HOLIDAYS


def outside_working_time(message, today=None):
    """True when the customer asks for a day or hour the crew does not work: a weekend, a public holiday, or a clock
    time before 9 am or from 6 pm ("3 am", "three AM"). Dates ("31 Oct", "tomorrow") are checked by their weekday.
    The days and hours come from the calendar's working rules."""
    from datetime import date as _date, timedelta
    from .calendar_scheduler import RULES
    today = today or _date.today()
    if not _NEGATED_DATE.search(message):
        days = RULES.working_days
        if (_SUNDAY.search(message) and 6 not in days) or (_SATURDAY.search(message) and 5 not in days) \
                or (_WEEKEND.search(message) and 5 not in days) or _HOLIDAY_NAMES.search(message):
            return True
        found = explicit_date(message)
        if found:
            try:
                if _closed_day(_date(found[2] or today.year, found[1], found[0]), days):
                    return True
            except ValueError:
                pass
        if (_TOMORROW.search(message) and _closed_day(today + timedelta(days=1), days)) \
                or (_TODAY.search(message) and _closed_day(today, days)):
            return True
    for found in _CLOCK.finditer(message):
        if found.group(3):
            hour = int(found.group(1)) % 12 + (12 if found.group(3).lower() == "pm" else 0)
        elif found.group(6):
            hour = _NUMBER_WORDS[found.group(6).lower()] % 12 + (12 if found.group(7).lower() == "pm" else 0)
        else:
            hour = int(found.group(4))
        if hour < RULES.day_start.hour or hour >= RULES.day_end.hour:
            return True
    return False


def date_problem(message, today=None):
    """A date answer that cannot be booked: 'date_past' (yesterday), 'date_past_year' ("20 Oct" when that day has gone
    by), 'date_closed' (weekend, public holiday, or 3 am) or 'date_need_day' ("after Raya"), else None."""
    if _PAST_DATE.search(message):
        return "date_past"
    if passed_this_year(message, today):
        return "date_past_year"
    if outside_working_time(message, today):
        return "date_closed"
    if _DATE_NEEDS_DAY.search(message) and not _DATE_WORDS.search(message):
        return "date_need_day"
    return None


_ASAP_TIME = re.compile(r"\b(asap|as soon as poss\w*|any ?time|whenever|soonest|secepat mungkin|secepatnya|bila-?bila)\b", re.I)
_DONT_KNOW = re.compile(r"\b(idk|dunno|don'?t know|do not know|no idea|tak tahu|entah|tak pasti)\b", re.I)
_RESTART = re.compile(r"\b(start over|start again|restart|begin again|from the start|mulakan semula|mula semula|"
                      r"mula balik)\b", re.I)


def wants_restart(message):
    return bool(_RESTART.search(message))


def restart_job(state):
    """The customer wants to begin the job from scratch (not a second job): drop the answers so far."""
    state.verified = {k: v for k, v in state.verified.items() if k in ("customer_name", "phone")}
    state.stage, state.quote, state.quote_status, state.photo_assessment = "job", None, "", None
    state.estimated, state.pending_conflict, state.history, state.last_field = [], None, [], ""
    state.waiting_count, state.attention, state.needs_human = 0, False, False
    state.service_checked = state.greeted = True


_QUESTION_START = re.compile(
    r"^\s*(do|does|can|could|what|whats|what's|how|which|is|are|will|would|any|apa|berapa|bila|boleh|adakah|"
    r"macam mana|bagaimana|siapa|di mana|kenapa|where|who|why|tell me|can i|do i|brp|bole|when|whens|when's)\b", re.I)
_FAQ_TOPICS = [
    ("faq_private", re.compile(r"\b(owner'?s?|boss'?s?)\s+(personal|phone|number|email|address|contact)|personal details|"
                               r"other customers?|admin panel|dashboard|system prompt|your instructions", re.I)),
    ("faq_bot", re.compile(r"\b(are you (a |an )?(bot|robot|ai|human|real|machine|person|chatgpt)|bot or|ai or|robot or|"
                           r"who are you|what'?s your name|what is your name|your name|siapa awak|nama awak|awak (robot|ai|manusia))\b", re.I)),
    ("faq_discount", re.compile(r"\b(discount|promo\w*|cheaper|lower the price|negotiat\w*|bargain|diskaun|kurangkan|"
                                r"murah sikit|best price|bulk|wholesale|many units|multiple units|minimum order)\b", re.I)),
    ("faq_prep", re.compile(r"\b(move (my |the )?furniture|furniture|cover(ing)? (the )?floor|not at home|nobody home|"
                            r"someone (home|there)|key|clean ?up|mess|dust|alih perabot|tiada di rumah)\b", re.I)),
    ("faq_time", re.compile(r"\b(how long|how many days|duration|berapa lama|takes? (long|time)|how soon)\b", re.I)),
    ("faq_avail", re.compile(r"\b(come (today|now|tomorrow|over|this)|available (today|now|tomorrow)|can you start|"
                             r"when (are|can|will|do) you|you free|your availability|book(ing)? (a |an )?(slot|appointment|time)|"
                             r"open now|opening hours|boleh datang|datang (hari ini|esok))\b", re.I)),
    ("faq_where", re.compile(r"\b(where (are|is) you|are you (located|based)|your (location|address|shop|office)|"
                             r"service area|do you (cover|serve)|which area|di mana|kawasan mana)\b", re.I)),
    ("faq_pay", re.compile(r"\b(pay|payment|deposit|installments?|cash|bank transfer|online banking|duitnow|tng|"
                           r"bayar\w*|ansuran)\b", re.I)),
    ("faq_warranty", re.compile(r"\b(warranty|guarantee|waranti|jaminan)\b", re.I)),
    ("faq_coats", re.compile(r"\b(coats?|undercoat|primer|lapisan)\b", re.I)),
    ("faq_wallpaper", re.compile(r"\b(wallpaper|scrap\w*|sanding|putty|plaster\w*|patch\w*|crack repair)\b", re.I)),
    ("faq_materials", re.compile(r"\b(provide|supply|bring|include[sd]?|buy|bekal\w*)\b.{0,25}\b(paint|materials?|cat)\b|"
                                 r"\b(paint|materials?)\b.{0,25}\b(included|provided|supplied|myself)\b", re.I)),
    ("faq_paint", re.compile(r"\b(dulux|nippon|jotun|brands?|jenama|what paint|which paint|apa cat)\b", re.I)),
    ("faq_compare", re.compile(r"\b(difference|different|compare|versus|vs|which is better|better than|beza)\b", re.I)),
    ("faq_whyaddress", re.compile(r"\bwhy\b.{0,25}\b(address|location)\b|\bkenapa\b.{0,20}\balamat\b", re.I)),
    ("faq_whyquestions", re.compile(r"\bwhy\b.{0,25}\b(so many|all these|all the) questions\b|\bkenapa\b.{0,20}\bbanyak soalan\b", re.I)),
    ("faq_offtopic", re.compile(r"\b(joke|weather|python|script|code|poem|song|recipe|football|bitcoin|crypto|stocks?|"
                                r"politic\w*|homework|translate)\b", re.I)),
]
_FAQ_SERVICES = re.compile(
    r"\b(services?|offer|other|else|what (do|can) you (offer|do|paint|provide|sell)|perkhidmatan|tawar\w*|lain|apa lagi)\b",
    re.I)
_FAQ_PRICE = re.compile(
    r"\b(price|prices|cost|costs|how much|expensive|cheap|charge|rates?|harga|kos|berapa|mahal|murah|bayar)\b",
    re.I)
_FAQ_PAINT = re.compile(
    r"\b(paints?|colou?rs?|brands?|quality|finish|cat|warna|jenama|kualiti)\b", re.I)


def faq_answer(message, config, stage="job", lang="en", force=False):
    """A fixed answer to a side question (services, price, paint), or None. Nothing here is invented:
    it only repeats the business's own configuration. While collecting the job only services and
    price are answered here, because the paint questions are part of the job itself."""
    if not force and "?" not in message and not _QUESTION_START.match(message):
        return None
    if len(message) > 140 and not _QUESTION_START.match(message):
        return None                     # a long message with a question tucked in is mostly about the job
    owner = _owner_for(config, lang)
    persona = config.get("persona") or {}
    for key, pattern in _FAQ_TOPICS:
        if pattern.search(message):
            if key == "faq_paint":
                tiers = list((config.get("pricing") or {}).get("paint_tiers", {})) or ["standard"]
                joiner = " atau " if lang == "ms" else " or "
                names = ", ".join(tiers[:-1]) + joiner + tiers[-1] if len(tiers) > 1 else tiers[0]
                return t("faq_paint", lang, tiers=names, owner=owner)
            return t(key, lang, owner=owner, name=persona.get("name") or owner, business=config.get("business_name", ""))
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


_CANCEL = re.compile(r"\b(cancel\w*|batal\w*|tak jadi|no longer (want|need)|dont want (it )?anymore|don'?t want (it )?anymore)\b", re.I)
_ANOTHER_ROOM = re.compile(r"\b(another|one more|also|too|next|lagi|juga)\b", re.I)
_RECOMMEND = re.compile(
    r"\b(recommend\w*|suggest\w*|advise|what (do|would|should) you|which (one|colou?r)|your opinion|help me (choose|pick|decide)|"
    r"cadang\w*|syor\w*|pilihkan)\b", re.I)


_RECAP = re.compile(r"\b(what did i (say|tell)|what('?s| is) my order|my order again|summary|recap|what do you have|"
                    r"apa yang saya (cakap|beritahu)|ringkasan)\b", re.I)


def asks_recap(message):
    return bool(_RECAP.search(message))


_CALL_OVER = re.compile(
    r"\b(bye|goodbye|good bye|that'?s all|that is all|nothing else|no more questions?|i'?m done|that'?s it|"
    r"selamat tinggal|itu sahaja|itu saja|tu je|dah habis)\b", re.I)


def ends_call(message):
    """The caller is saying goodbye ("ok thanks, bye", "that's all"): a short message, not "bye the way..."."""
    return len(message.split()) <= 8 and bool(_CALL_OVER.search(message))


def wants_cancel(message):
    return bool(_CANCEL.search(message))


def asks_for_ideas(message):
    return bool(_RECOMMEND.search(message))


_THANKS = {"thanks", "thank", "thx", "tq", "ty", "terima", "kasih", "tqvm", "cheers"}
_BYE = {"bye", "goodbye", "cya", "tata", "babai", "later"}
_HELLO = {"hi", "hello", "hey", "hai", "helo", "hye", "anyone", "there", "ping", "oi", "yo"}
_OKAY = {"ok", "okay", "okey", "hmm", "hm", "um", "uh", "so", "sure", "yes", "yeah", "ya", "yep", "ye", "alright",
         "oh", "ah", "lol", "haha", "k", "kk", "noted", "no", "nope"}


def smalltalk(message):
    """What a short message with no job in it is: hello | thanks | bye | okay | confused (only symbols)."""
    text = message.strip().lower()
    if not re.search(r"[a-z0-9]", text):
        return "confused"
    words = re.findall(r"[a-z']+", text)
    if not words or len(words) > 5 or re.search(r"\d", text):
        return None
    if set(words) & _THANKS:
        return "thanks"
    if set(words) & _BYE:
        return "bye"
    if set(words) <= _HELLO | {"is", "are", "you", "u", "there", "here", "any", "body", "one"}:
        return "hello"
    if set(words) <= _OKAY | {"ok", "then"}:
        return "okay"
    return None


# --- changing their mind ------------------------------------------------------------------------
CORRECTION = re.compile(
    r"\b(nvm|nevermind|never mind|actually|sorry|my bad|i mean|correction|wait|no it'?s|not \d|make it|"
    r"change (it )?to|instead|rather|wrong|mistake|oops|silap|salah|maaf|bukan|sebenarnya|tukar|ubah|"
    r"maksud saya|eh|lupa|tak jadi)\b", re.I)


def is_correction(message):
    if CORRECTION.search(message):
        return True
    short_size = r"\s*(?:no|ok|okay|so)?\b[\s,.]*(?:final(?:ly)?)?[\s,.]*\d+(?:[.,]\d+)?\s*(?:m|cm|ft|feet|meters?|metres?|kaki)?\s*[.!]*\s*"
    return bool(re.fullmatch(short_size, message, re.I)) and bool(re.search(r"\b(no|final|finally)\b", message, re.I))


# a message that swaps an earlier answer for another ("change colour to blue", "grey is better", "make it saturday")
SWAP = re.compile(r"\b(nvm|nevermind|never mind|actually|sorry|wait|no|not|make it|change|switch|instead|rather|"
                  r"better|stick with|go with|prefer|rather|tukar|ubah|bukan|sebenarnya|maaf|lebih baik|pilih)\b", re.I)


# --- repeat customers ---------------------------------------------------------------------------
_AGAIN = re.compile(
    r"\b(another|new|also|one more|again|different|other|next|second|lagi|baru|lain|satu lagi|juga|pula)\b", re.I)
_WANT = re.compile(r"\b(want|need|like|looking|planning|nak|mahu|hendak|perlu|ingin)\b", re.I)


_NEW_JOB_WORDS = re.compile(
    r"\b(?:another|a\s+new|new|second|next|one\s+more|lagi|baru)\s+(?:job|jobs|quote|quotation|booking|order|project|one|kerja)\b|"
    r"\b(?:start|begin)\s+(?:again|over|afresh|a\s+new\s+\w+)\b|\bmula\s+(?:semula|balik)\b", re.I)


def new_job_intent(message, state):
    """A customer who already finished a job asks for another one."""
    if state.stage == "done" and _NEW_JOB_WORDS.search(message):
        return True                     # "I want another job", "start again": no need to name the paint work again
    if not (_SUPPORTED.search(message) and _WANT.search(message)):
        return False
    if (SWAP.search(message) or is_correction(message)) and not re.search(r"\b(another|new|second|next|lagi|baru)\b", message, re.I):
        return False                    # "actually I want premium instead" changes this job, it is not a new one
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


_GREETING = re.compile(r"^\s*(hi|hello|hey|hai|helo|hye|hy|yo|assalamualaikum|salam)\b[\s!.?,a-z]{0,20}$", re.I)


def after_done(state, message, config):
    """The reply once the chat is complete, or None to stay silent. While the SME has not confirmed, the
    bot answers real questions and anything important (and flags it), acknowledges a couple of other
    messages, then stops replying so the customer is not answered in circles."""
    lang, owner = state.lang, _owner_for(config, state.lang)
    waiting = state.quote_status in ("", "pending_approval", "needs_inspection", "rejected")
    if len(state.followups) < 50:
        state.followups.append({"text": message[:300], "at": time.time()})
    faq = faq_answer(message, config, "done", lang)
    if _GREETING.match(message) and state.quote_status in ("approved", "final"):
        return t("welcome_back", lang)               # a returning customer saying hello
    if _DATE_WORDS.search(message) and date_problem(message) in ("date_past", "date_past_year", "date_closed"):
        return t(date_problem(message), lang)           # a date that has gone by: ask again, keep the old preference
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
