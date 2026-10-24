"""Booking the job: slot suggestions that keep one area's jobs close together.

Built on the team's calendar_scheduler (working hours, Asia/Kuala_Lumpur, search window). That module finds the
first free slot; this one scores several candidate slots so jobs near each other in the same area land on the
same day, back to back, which saves the crew travel time. Bookings live in the store, so the dashboard, the
WhatsApp confirmation and the suggestions all see the same calendar.
"""
import re
import uuid
from datetime import date, datetime, timedelta

from .calendar_scheduler import RULES, TZ

POSTCODE = re.compile(r"\b(\d{5})\b")
TRAVEL_MINUTES = {"same": 15, "near": 30, "far": 45}     # gap kept between jobs of different customers
ACTIVE = ("confirmed", "tentative")


def parse_time(value):
    if isinstance(value, str) and value[-6:-5] == " ":      # a "+" in a query string arrives as a space
        value = value[:-6] + "+" + value[-5:]
    moment = datetime.fromisoformat(value) if isinstance(value, str) else value
    return moment.replace(tzinfo=TZ) if moment.tzinfo is None else moment.astimezone(TZ)


def area_of(address):
    """The part of an address that says where it is: the postcode (its first 3 digits cover a district) and
    the town after the last comma. {} when the address says neither."""
    text = address or ""
    out = {}
    match = POSTCODE.search(text)
    if match:
        out["postcode"], out["prefix"] = match.group(1), match.group(1)[:3]
    parts = [p.strip().lower() for p in text.split(",") if p.strip()]
    if len(parts) >= 2:
        town = re.sub(r"\d+", "", parts[-1]).strip()
        if town:
            out["name"] = town
    return out


def closeness(a, b):
    """same (same postcode) | near (same district or town) | far (or unknown)."""
    if a.get("postcode") and a.get("postcode") == b.get("postcode"):
        return "same"
    if (a.get("prefix") and a.get("prefix") == b.get("prefix")) or (a.get("name") and a.get("name") == b.get("name")):
        return "near"
    return "far"


def day_segments(start, hours, rules=RULES):
    """The working blocks of a job that starts at `start`: one block per day, a long job continues at the next
    working day's opening time."""
    segments, remaining, cursor = [], float(hours), start
    while remaining > 1e-9:
        close = datetime.combine(cursor.date(), rules.day_end, TZ)
        room = max((close - cursor).total_seconds() / 3600, 0)
        take = min(remaining, room) if room else 0
        if take:
            segments.append((cursor, cursor + timedelta(hours=take)))
            remaining -= take
        day = cursor.date() + timedelta(days=1)
        while day.weekday() not in rules.working_days:
            day += timedelta(days=1)
        cursor = datetime.combine(day, rules.day_start, TZ)
    return segments


def booking_segments(booking, rules=RULES):
    return day_segments(parse_time(booking["start"]), booking.get("hours") or 1, rules)


def _round_up(moment, step_minutes):
    moment = moment.replace(second=0, microsecond=0)
    extra = moment.minute % step_minutes
    return moment + timedelta(minutes=step_minutes - extra) if extra else moment


def _busy(bookings, ignore_id=None, rules=RULES):
    """(segment start, segment end, booking) for every active booking."""
    return [(s, e, b) for b in bookings if b["status"] in ACTIVE and b["id"] != ignore_id
            for s, e in booking_segments(b, rules)]


def _free(segments, busy, extra_busy, area, rules):
    for start, end in segments:
        for other_start, other_end, other in busy:
            gap = timedelta(minutes=TRAVEL_MINUTES[closeness(area, other.get("area", {}))])
            if other_start - gap < end and other_end + gap > start:
                return False
        for other_start, other_end in extra_busy:
            if other_start < end and other_end > start:
                return False
    return True


def conflicts(bookings, start, hours, address="", ignore_id=None, extra_busy=(), rules=RULES):
    """True when the job would overlap an existing booking (with travel time) or an outside event."""
    segments = day_segments(parse_time(start), hours, rules)
    extra = [(parse_time(s), parse_time(e)) for s, e in extra_busy]
    return not _free(segments, _busy(bookings, ignore_id, rules), extra, area_of(address), rules)


def suggest_slots(bookings, hours, address="", now=None, rules=RULES, extra_busy=(), limit=6, ignore_id=None):
    """Best start times for a job of `hours` on site, best first: {start, end, score 0-100, reason}.
    Earlier is better, and a slot right after or on the same day as a job in the same area scores higher."""
    now = now or datetime.now(TZ)
    hours = max(float(hours or 4), 0.5)
    area = area_of(address)
    busy = _busy(bookings, ignore_id, rules)
    extra = [(parse_time(s), parse_time(e)) for s, e in extra_busy]
    candidates = {}
    for offset in range(rules.search_days + 1):
        day = now.date() + timedelta(days=offset)
        if day.weekday() not in rules.working_days:
            continue
        opening = datetime.combine(day, rules.day_start, TZ)
        starts = [opening]
        if offset == 0:
            starts.append(_round_up(now, rules.step_minutes))
        for seg_start, seg_end, other in busy:        # right after a nearby job that day
            if seg_end.date() == day and closeness(area, other.get("area", {})) != "far":
                starts.append(_round_up(seg_end + timedelta(minutes=TRAVEL_MINUTES[closeness(area, other["area"])]),
                                        rules.step_minutes))
        for start in starts:
            close = datetime.combine(day, rules.day_end, TZ)
            if start <= now or start < opening or start >= close:
                continue
            segments = day_segments(start, hours, rules)
            if start in candidates or not _free(segments, busy, extra, area, rules):
                continue
            score, reason = 80 - 2 * offset, "Free time"
            for seg_start, seg_end, other in busy:
                kind = closeness(area, other.get("area", {}))
                if kind == "far":
                    continue
                days_apart = min(abs((s_.date() - seg_start.date()).days) for s_, _ in segments)
                adjacent = any(abs((s_ - seg_end).total_seconds()) <= 3600 or abs((seg_start - e_).total_seconds()) <= 3600
                               for s_, e_ in segments)
                bonus, why = {
                    ("same", 0, True): (30, "Right after {name}, same postcode"),
                    ("same", 0, False): (22, "Same day as {name}, same postcode"),
                    ("same", 1, False): (10, "Day next to {name}, same postcode"),
                    ("near", 0, True): (22, "Right after {name}, same area"),
                    ("near", 0, False): (15, "Same day as {name}, same area"),
                    ("near", 1, False): (6, "Day next to {name}, same area"),
                }.get((kind, days_apart if days_apart <= 1 else 9, adjacent and days_apart == 0), (0, ""))
                if bonus and 80 - 2 * offset + bonus > score:
                    score, reason = 80 - 2 * offset + bonus, why.format(name=other.get("customer") or "another job")
            candidates[start] = {"start": segments[0][0].isoformat(), "end": segments[-1][1].isoformat(),
                                 "score": max(0, min(100, int(score))), "reason": reason}
    plain = sorted((c for c in candidates.values() if c["reason"] == "Free time"), key=lambda c: c["start"])
    if plain:
        plain[0]["reason"] = "Earliest free time"
    ranked = sorted(candidates.values(), key=lambda c: (-c["score"], c["start"]))
    return ranked[:limit]


def new_booking(user_id, customer, phone, address, start, hours, status="tentative", rules=RULES):
    segments = day_segments(parse_time(start), hours, rules)
    return {"id": uuid.uuid4().hex[:12], "user_id": user_id, "customer": customer or "Customer", "phone": phone or "",
            "address": address or "", "area": area_of(address), "start": segments[0][0].isoformat(),
            "end": segments[-1][1].isoformat(), "hours": float(hours), "status": status,
            "created_at": datetime.now(TZ).isoformat()}


def describe_when(start, lang="en"):
    """"Mon 26 Oct, 9:00 am" in the customer's language."""
    moment = parse_time(start)
    days = (["Isnin", "Selasa", "Rabu", "Khamis", "Jumaat", "Sabtu", "Ahad"] if lang == "ms"
            else ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
    months = (["Jan", "Feb", "Mac", "Apr", "Mei", "Jun", "Jul", "Ogos", "Sep", "Okt", "Nov", "Dis"] if lang == "ms"
              else ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
    hour = moment.hour % 12 or 12
    return f"{days[moment.weekday()]} {moment.day} {months[moment.month - 1]}, {hour}:{moment.minute:02d} {'am' if moment.hour < 12 else 'pm'}"
