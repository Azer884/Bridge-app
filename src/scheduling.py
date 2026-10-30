"""Booking the job: slot suggestions that keep one area's jobs close together.

Built on the team's calendar_scheduler (working hours, Asia/Kuala_Lumpur, search window). That module finds the
first free slot; this one scores several candidate slots so jobs near each other in the same area land on the
same day, back to back, which saves the crew travel time. Bookings live in the store, so the dashboard, the
WhatsApp confirmation and the suggestions all see the same calendar.
"""
import math
import re
import uuid
from datetime import date, datetime, time, timedelta

from .calendar_scheduler import RULES, TZ

POSTCODE = re.compile(r"\b(\d{5})\b")
TRAVEL_MINUTES = {"same": 15, "near": 30, "far": 45}     # gap kept between jobs of different customers
ACTIVE = ("confirmed", "tentative")


def parse_time(value):
    if isinstance(value, str) and value[-6:-5] == " ":      # a "+" in a query string arrives as a space
        value = value[:-6] + "+" + value[-5:]
    moment = datetime.fromisoformat(value) if isinstance(value, str) else value
    return moment.replace(tzinfo=TZ) if moment.tzinfo is None else moment.astimezone(TZ)


def km_between(a, b):
    """Straight-line distance in km between two {"lat", "lon"} points."""
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dlat, dlon = p2 - p1, math.radians(b["lon"] - a["lon"])
    h = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def area_of(address, location=None):
    """Where a job is: the postcode (its first 3 digits cover a district), the town after the last comma, and the
    coordinates when the customer shared a location. {} when nothing says."""
    text = address or ""
    out = {}
    if location and location.get("lat") is not None and location.get("lon") is not None:
        out["lat"], out["lon"] = float(location["lat"]), float(location["lon"])
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
    """same (same postcode, or under 2 km apart) | near (same district or town, or under 15 km) | far (or unknown)."""
    if "lat" in a and "lat" in b:
        km = km_between(a, b)
        return "same" if km < 2 else "near" if km < 15 else "far"
    if a.get("postcode") and a.get("postcode") == b.get("postcode"):
        return "same"
    if (a.get("prefix") and a.get("prefix") == b.get("prefix")) or (a.get("name") and a.get("name") == b.get("name")):
        return "near"
    return "far"


WEEKDAYS = {"monday": 0, "mon": 0, "tuesday": 1, "tues": 1, "tue": 1, "wednesday": 2, "wed": 2, "thursday": 3,
            "thurs": 3, "thur": 3, "thu": 3, "friday": 4, "fri": 4, "saturday": 5, "sat": 5, "sunday": 6, "sun": 6,
            "isnin": 0, "selasa": 1, "rabu": 2, "khamis": 3, "jumaat": 4, "sabtu": 5, "ahad": 6}
PARTS = {"morning": (9, 12), "pagi": (9, 12), "afternoon": (12, 16), "evening": (15, 18), "tonight": (15, 18),
         "night": (15, 18), "malam": (15, 18), "petang": (15, 18)}
MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10,
          "nov": 11, "dec": 12, "mac": 3, "mei": 5, "ogos": 8, "dis": 12}


def parse_preference(text, anchor=None, today=None):
    """What the customer asked for, read from their own words ("Monday evening", "tomorrow 8am", "26 Oct"):
    {"date", "weekday", "part", "hour", "after", "text"}; empty values mean they did not say. Relative words
    ("tomorrow") count from `anchor`, the day they said it."""
    anchor = anchor or datetime.now(TZ)
    low = (text or "").lower()
    pref = {"date": None, "weekday": None, "part": None, "hour": None, "after": None, "text": (text or "").strip()}
    words = re.findall(r"[a-z]+", low)
    if "tomorrow" in words or "esok" in words:
        pref["date"] = (anchor + timedelta(days=1)).date()
    elif "today" in words or "tonight" in words:
        pref["date"] = anchor.date()
    elif "lusa" in words:
        pref["date"] = (anchor + timedelta(days=2)).date()
    for word in words:
        if word in WEEKDAYS and not pref["date"]:
            pref["weekday"] = WEEKDAYS[word]
        if word in PARTS and not pref["part"]:
            pref["part"] = word if word in ("morning", "afternoon", "evening") else {"pagi": "morning"}.get(word, "evening")
    from .flow import explicit_date
    today = today or anchor.date()      # the service passes today's date: a day that has gone by is never offered
    found = explicit_date(text or "")
    if found:
        day, month, year = found
        try:
            chosen = date(year or anchor.year, month, day)
            if year is None and chosen < today:
                chosen = date(chosen.year + 1, month, day)
            pref["date"] = chosen
        except ValueError:
            pass
    slash = re.search(r"\b(\d{1,2})[/.-](\d{1,2})\b", low)
    if slash and not pref["date"]:
        try:
            chosen = date(anchor.year, int(slash.group(2)), int(slash.group(1)))
            pref["date"] = chosen if chosen >= anchor.date() else date(anchor.year + 1, chosen.month, chosen.day)
        except ValueError:
            pass
    clock = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", low)
    if clock:
        hour = int(clock.group(1)) % 12 + (12 if clock.group(3) == "pm" else 0)
        pref["hour"] = hour
        pref["part"] = pref["part"] or ("morning" if hour < 12 else "afternoon" if hour < 15 else "evening")
    if "next week" in low or "minggu depan" in low:
        pref["after"] = (anchor + timedelta(days=7 - anchor.weekday())).date()
    return pref


def _wanted(pref, start, hours):
    """(bonus, matches) for a slot against the customer's preference."""
    if not pref or not any(pref.get(k) is not None for k in ("date", "weekday", "part", "hour", "after")):
        return 0, []
    bonus, matched = 0, []
    day = start.date()
    if pref.get("date") is not None:
        if day == pref["date"]:
            bonus, matched = bonus + 40, matched + ["day"]
    elif pref.get("weekday") is not None:
        if day.weekday() == pref["weekday"]:
            bonus, matched = bonus + 40, matched + ["day"]
    elif pref.get("after") is not None and day >= pref["after"]:
        bonus, matched = bonus + 15, matched + ["week"]
    if pref.get("hour") is not None:
        if abs(start.hour + start.minute / 60 - pref["hour"]) <= 1:
            bonus, matched = bonus + 25, matched + ["time"]
    elif pref.get("part"):
        low, high = PARTS[pref["part"]]
        end_hour = start.hour + start.minute / 60 + hours
        if low <= start.hour + start.minute / 60 and (end_hour <= high + 3 if pref["part"] == "evening" else start.hour < high):
            bonus, matched = bonus + 25, matched + ["time"]
    return bonus, matched


# Malaysia's Employment Act 1955: at most 8 working hours a day, never more than 5 hours in a row without a break of
# at least 30 minutes, and at most 45 hours a week. The crew works 9:00-13:00 and 14:00-18:00 (8 hours, an hour's lunch
# break) Monday to Friday and 9:00-13:00 on Saturday: 44 hours a week. A longer job continues on the next working day.
LUNCH = (time(13, 0), time(14, 0))
SATURDAY_CLOSE = time(13, 0)
MAX_HOURS_PER_DAY = 8


def work_windows(day, rules=RULES):
    """The crew's working periods on `day` as (start, end) datetimes; [] on a day off."""
    if day.weekday() not in rules.working_days:
        return []
    opening, close = rules.day_start, SATURDAY_CLOSE if day.weekday() == 5 else rules.day_end
    windows = []
    if opening < LUNCH[0] < close:
        windows.append((opening, LUNCH[0]))
        if LUNCH[1] < close:
            windows.append((LUNCH[1], close))
    else:
        windows.append((opening, close))
    out, total = [], 0.0
    for a, b in windows:                               # never more than 8 hours in a day, whatever the rules say
        start, end = datetime.combine(day, a, TZ), datetime.combine(day, b, TZ)
        room = min((end - start).total_seconds() / 3600, MAX_HOURS_PER_DAY - total)
        if room > 0:
            out.append((start, start + timedelta(hours=room)))
            total += room
    return out


def day_close(day, rules=RULES):
    windows = work_windows(day, rules)
    return windows[-1][1] if windows else None


def day_segments(start, hours, rules=RULES):
    """The working blocks of a job that starts at `start`: the morning and afternoon of each working day, with the
    lunch break kept free. A job longer than a day continues the next working day at opening time."""
    segments, remaining, cursor = [], float(hours), start
    for _ in range(400):                               # a year of working days is more than any painting job
        if remaining <= 1e-9:
            break
        for opening, close in work_windows(cursor.date(), rules):
            if close <= cursor or remaining <= 1e-9:
                continue
            begin = max(opening, cursor)
            take = min(remaining, (close - begin).total_seconds() / 3600)
            if take > 1e-9:
                segments.append((begin, begin + timedelta(hours=take)))
                remaining -= take
        day = cursor.date() + timedelta(days=1)
        cursor = datetime.combine(day, rules.day_start, TZ)
    return segments


def working_days(segments):
    """[(day start, day end)] per calendar day of the job: one block for each day the crew is there."""
    days = {}
    for start, end in segments:
        first, last = days.get(start.date(), (start, end))
        days[start.date()] = (min(first, start), max(last, end))
    return [days[d] for d in sorted(days)]


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


def conflicts(bookings, start, hours, address="", ignore_id=None, extra_busy=(), rules=RULES, location=None):
    """True when the job would overlap an existing booking (with travel time) or an outside event."""
    segments = day_segments(parse_time(start), hours, rules)
    extra = [(parse_time(s), parse_time(e)) for s, e in extra_busy]
    return not _free(segments, _busy(bookings, ignore_id, rules), extra, area_of(address, location), rules)


def suggest_slots(bookings, hours, address="", now=None, rules=RULES, extra_busy=(), limit=6, ignore_id=None,
                  preference=None, location=None):
    """Best start times for a job of `hours` on site, best first: {start, end, score 0-100, reason}.
    Earlier is better, and a slot right after or on the same day as a job in the same area scores higher."""
    now = now or datetime.now(TZ)
    hours = max(float(hours or 4), 0.5)
    area = area_of(address, location)
    if preference and preference.get("date") is not None:
        wanted_day = preference["date"]                  # a preferred day that is not a working day moves to the next one
        while wanted_day.weekday() not in rules.working_days:
            wanted_day += timedelta(days=1)
        preference = {**preference, "date": wanted_day}
    busy = _busy(bookings, ignore_id, rules)
    extra = [(parse_time(s), parse_time(e)) for s, e in extra_busy]
    candidates = {}
    for offset in range(rules.search_days + 1):
        day = now.date() + timedelta(days=offset)
        if day.weekday() not in rules.working_days:
            continue
        if not work_windows(day, rules):
            continue
        opening = datetime.combine(day, rules.day_start, TZ)
        starts = [opening, datetime.combine(day, LUNCH[1], TZ)]
        close_of_day = day_close(day, rules)
        if preference:                                  # start times that fit what the customer asked for
            latest = close_of_day - timedelta(hours=min(hours, MAX_HOURS_PER_DAY))
            starts += [datetime.combine(day, time(13, 0), TZ), latest.replace(minute=latest.minute - latest.minute % 30)]
            if preference.get("hour") is not None:
                starts.append(datetime.combine(day, time(preference["hour"], 0), TZ))
            elif preference.get("part") in PARTS:             # "evening": a start at the beginning of that part of the day
                starts.append(datetime.combine(day, time(PARTS[preference["part"]][0], 0), TZ))
        if offset == 0:
            starts.append(_round_up(now, rules.step_minutes))
        for seg_start, seg_end, other in busy:        # right after a nearby job that day
            if seg_end.date() == day and closeness(area, other.get("area", {})) != "far":
                starts.append(_round_up(seg_end + timedelta(minutes=TRAVEL_MINUTES[closeness(area, other["area"])]),
                                        rules.step_minutes))
        for start in starts:
            close = close_of_day
            if start <= now or start < opening or start >= close or LUNCH[0] <= start.time() < LUNCH[1]:
                continue
            segments = day_segments(start, hours, rules)
            if start in candidates or not _free(segments, busy, extra, area, rules):
                continue
            first_day = segments[0][0].date()
            first_day_hours = sum((e - s).total_seconds() / 3600 for s, e in segments if s.date() == first_day)
            wanted, matched = _wanted(preference, segments[0][0], first_day_hours)
            score, reason = 80 - 2 * offset + wanted, "Free time"
            if matched:
                said = preference["text"][:40]
                reason = (f'Matches what the customer asked for ("{said}")' if "time" in matched
                          else f'Day the customer asked for ("{said}")')
            cluster = 0
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
                if bonus > cluster:
                    cluster, why_cluster = bonus, why.format(name=other.get("customer") or "another job")
            if cluster:
                score += cluster
                reason = why_cluster if not matched else f"{reason}; {why_cluster[0].lower()}{why_cluster[1:]}"
            candidates[start] = {"start": segments[0][0].isoformat(), "end": segments[-1][1].isoformat(),
                                 "score": max(0, min(100, int(score))), "reason": reason, "_raw": score}
    plain = sorted((c for c in candidates.values() if c["reason"] == "Free time"), key=lambda c: c["start"])
    if plain:
        plain[0]["reason"] = "Earliest free time"
    ranked = sorted(candidates.values(), key=lambda c: (-c["_raw"], c["start"]))     # the raw score keeps ties apart
    top = max((c["_raw"] for c in ranked), default=100)
    scale = 100 / top if top > 100 else 1                   # keep the best at 100 and the rest in proportion
    return [{**{k: v for k, v in c.items() if k not in ("_raw", "score")}, "score": max(0, int(c["_raw"] * scale))}
            for c in ranked[:limit]]


def new_booking(user_id, customer, phone, address, start, hours, status="tentative", rules=RULES, location=None):
    segments = day_segments(parse_time(start), hours, rules)
    return {"id": uuid.uuid4().hex[:12], "user_id": user_id, "customer": customer or "Customer", "phone": phone or "",
            "address": address or "", "area": area_of(address, location), "start": segments[0][0].isoformat(),
            "end": segments[-1][1].isoformat(), "hours": float(hours), "status": status,
            "location": location, "created_at": datetime.now(TZ).isoformat()}


def describe_days(booking, lang="en"):
    """A job that runs over several working days, day by day: "Day 1: Mon 9 Nov, 2:00 pm to 6:00 pm; Day 2: ...".
    Empty for a job that fits in one day."""
    days = working_days(booking_segments(booking))
    if len(days) <= 1:
        return ""
    word = "Hari" if lang == "ms" else "Day"

    def clock(moment):
        return f"{moment.hour % 12 or 12}:{moment.minute:02d} {'am' if moment.hour < 12 else 'pm'}"
    return "; ".join(f"{word} {number}: {describe_when(start.isoformat(), lang).split(',')[0]}, {clock(start)} - {clock(end)}"
                     for number, (start, end) in enumerate(days, start=1))


def describe_when(start, lang="en"):
    """"Mon 26 Oct, 9:00 am" in the customer's language."""
    moment = parse_time(start)
    days = (["Isnin", "Selasa", "Rabu", "Khamis", "Jumaat", "Sabtu", "Ahad"] if lang == "ms"
            else ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
    months = (["Jan", "Feb", "Mac", "Apr", "Mei", "Jun", "Jul", "Ogos", "Sep", "Okt", "Nov", "Dis"] if lang == "ms"
              else ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
    hour = moment.hour % 12 or 12
    return f"{days[moment.weekday()]} {moment.day} {months[moment.month - 1]}, {hour}:{moment.minute:02d} {'am' if moment.hour < 12 else 'pm'}"
