"""Demo data for filming: believable customers around the Klang Valley, their WhatsApp chats, priced estimates in
every state and a busy fortnight in the calendar, including one job that runs over three working days.

Everything is created through the real pricing engine and scheduler, so the numbers, durations and day splits are
the ones the app would produce. Every id starts with "demo-"; POST /api/demo/seed replaces it and DELETE removes it.
"""
import time
from datetime import datetime, timedelta

from . import scheduling, views
from .conversation import ConversationState

CUSTOMERS = [
    {"id": "demo-60123456701", "name": "Siti Aminah", "phone": "+60123456701", "lang": "en",
     "address": "12 Jalan Bunga Raya, Taman Melati, 53100 Kuala Lumpur", "status": "approved", "booking": "confirmed",
     "day": 1, "hour": 9,
     "job": {"surfaces": ["walls", "ceiling"], "room_length_m": 5.0, "room_width_m": 4.0, "room_height_m": 3.0,
             "room_name": "living room", "surface_condition": "good", "paint_tier": "premium", "colour": "cream",
             "preferred_datetime": "Monday morning"},
     "chat": ["Hi, I'd like a quote to repaint my living room",
              "Hi there, I'm Aisha from Example Painting! Which surfaces would you like painted?",
              "Walls and ceiling, it's 5 by 4 and 3 meters high",
              "Got it. What paint quality would you like: economy, standard or premium?",
              "Premium please, in cream", "Noted. When would you like us to come over?", "Monday morning"]},
    {"id": "demo-60198765402", "name": "Ahmad Faizal", "phone": "+60198765402", "lang": "ms",
     "address": "No 8 Jalan Mawar 3, Seksyen 7, 40000 Shah Alam", "status": "approved", "booking": "confirmed",
     "day": 2, "hour": 9,
     "job": {"surfaces": ["walls"], "room_length_m": 4.0, "room_width_m": 4.0, "room_height_m": 3.0,
             "room_name": "bedroom 1", "surface_condition": "baik", "paint_tier": "standard", "colour": "putih",
             "preferred_datetime": "minggu depan",
             "extra_rooms": [{"name": "bedroom 2", "room_length_m": 4.0, "room_width_m": 4.0, "room_height_m": 3.0},
                             {"name": "bedroom 3", "room_length_m": 3.5, "room_width_m": 3.0, "room_height_m": 3.0},
                             {"name": "ruang tamu", "room_length_m": 6.0, "room_width_m": 5.0, "room_height_m": 3.0}]},
     "chat": ["Salam, nak cat rumah saya, 3 bilik tidur dan ruang tamu",
              "Hai, saya Aisha dari Example Painting! Boleh beri saiz setiap bilik?",
              "Bilik 1 dan 2 4 x 4 x 3, bilik 3 3.5 x 3 x 3, ruang tamu 6 x 5 x 3",
              "Baik, setakat ini 4 bilik. Apakah kualiti cat yang anda mahu?", "Standard, warna putih"]},
    {"id": "demo-60172233403", "name": "Priya Raman", "phone": "+60172233403", "lang": "en",
     "address": "23 Jalan SS 2/24, SS 2, 47300 Petaling Jaya", "status": "approved", "booking": "tentative",
     "day": 6, "hour": 14,
     "job": {"surfaces": ["walls"], "room_length_m": 3.5, "room_width_m": 3.0, "room_height_m": 2.8,
             "room_name": "kids room", "surface_condition": "some peeling near the window", "paint_tier": "standard",
             "colour": "light blue", "preferred_datetime": "next week afternoon"},
     "chat": ["Hello, can you paint my kids room? 3.5 by 3, height 2.8",
              "Hi there, I'm Aisha from Example Painting! What condition are the walls in?",
              "Some peeling near the window", "Thanks. Which colour would you like?", "Light blue"]},
    {"id": "demo-60126677404", "name": "Jason Lim", "phone": "+60126677404", "lang": "en",
     "address": "5 Jalan USJ 9/5Q, Subang Business Centre, 47620 Subang Jaya", "status": "approved",
     "booking": "confirmed", "day": 1, "hour": 14,
     "job": {"surfaces": ["one wall"], "room_length_m": 4.5, "room_height_m": 3.0, "surface_condition": "good",
             "paint_tier": "premium", "colour": "dark grey accent", "preferred_datetime": "Monday afternoon"},
     "chat": ["Need one accent wall painted dark grey, 4.5m long 3m high", "Got it. What paint quality would you like?",
              "Premium", "Noted. When suits you?", "Monday afternoon"]},
    {"id": "demo-60135544305", "name": "Nurul Huda", "phone": "+60135544305", "lang": "ms",
     "address": "18 Jalan Cheras Hartamas, Taman Cheras Hartamas, 43200 Cheras", "status": "pending_approval",
     "job": {"surfaces": ["walls", "ceiling"], "room_length_m": 4.0, "room_width_m": 3.5, "room_height_m": 2.8,
             "room_name": "dapur", "surface_condition": "kesan kotoran minyak", "paint_tier": "economy",
             "colour": "krim", "preferred_datetime": "Sabtu pagi"},
     "chat": ["Hai, nak cat dapur, 4 x 3.5, tinggi 2.8", "Baik. Bagaimana keadaan dinding?",
              "Ada kesan kotoran minyak", "Terima kasih. Apakah kualiti cat yang anda mahu?", "Ekonomi, warna krim"]},
    {"id": "demo-60163322106", "name": "David Tan", "phone": "+60163322106", "lang": "en",
     "address": "40 Jalan Telawi 3, Bangsar Baru, 59100 Kuala Lumpur", "status": "needs_inspection",
     "job": {"surfaces": ["walls", "ceiling"], "room_length_m": 5.0, "room_width_m": 4.5, "room_height_m": 3.2,
             "room_name": "master bedroom", "surface_condition": "damp patches and mould near the bathroom wall",
             "paint_tier": "premium", "colour": "white", "preferred_datetime": "as soon as possible"},
     "chat": ["Master bedroom 5 x 4.5, 3.2 high, there's damp and mould near the bathroom",
              "Thanks for letting us know. That kind of work needs an inspection, so a member of our team will contact you."]},
    {"id": "demo-60187788907", "name": "Mei Ling Wong", "phone": "+60187788907", "lang": "en",
     "address": "7 Jalan Damansara Utama, SS 21, 47400 Petaling Jaya", "status": "approved", "booking": "confirmed",
     "day": 4, "hour": 9,
     "job": {"surfaces": ["walls"], "room_length_m": 6.0, "room_width_m": 5.0, "room_height_m": 3.0,
             "room_name": "office", "surface_condition": "good", "paint_tier": "standard", "colour": "warm white",
             "preferred_datetime": "Thursday"},
     "chat": ["Hi, quote for my home office walls please, 6 by 5 by 3", "Got it. Which paint quality would you like?",
              "Standard, warm white", "When would you like us to come?", "Thursday"]},
]


def _working_day(now, offset):
    """The `offset`-th working day after today (1 is the next one)."""
    day, found = now.date(), 0
    while found < offset:
        day += timedelta(days=1)
        if scheduling.work_windows(day):
            found += 1
    return day


def seed(service, now=None):
    now = now or datetime.now(scheduling.TZ)
    store, made, booked = service.store, 0, 0
    for c in CUSTOMERS:
        state = ConversationState(c["id"])
        state.channel = {"name": c["name"], "phone": c["phone"]}
        state.verified = {**c["job"], "address": c["address"], "customer_name": c["name"], "phone": c["phone"]}
        state.lang, state.stage, state.greeted, state.service_checked = c["lang"], "done", True, True
        state.contact_confirmed, state.created_at = True, time.time() - 3600 * (made + 2)
        quote = service._price(state)
        if quote is None:
            continue
        state.quote = quote.to_dict()
        state.quote_status = c["status"]
        if c["status"] == "approved":
            state.quote["approved_total"] = state.quote["total"]
        state.needs_human = state.attention = c["status"] == "needs_inspection"
        for number, text in enumerate(c["chat"]):
            store.log_message(c["id"], "in" if number % 2 == 0 else "out", text)
        store.add_audit(c["id"], "ai", "ai_extraction", "The assistant collected the job details")
        store.add_audit(c["id"], "system", "calculation",
                        f"Draft estimate calculated: {quote.currency} {quote.total:,.2f}")
        if c["status"] == "approved":
            store.add_audit(c["id"], "owner", "state_change", f"Estimate approved: {quote.currency} {quote.total:,.2f}")
        store.save(state)
        made += 1
        if c.get("booking"):
            hours = service._job_hours(state)
            day = _working_day(now, c["day"])
            start = datetime.combine(day, datetime.min.time().replace(hour=c["hour"]), scheduling.TZ)
            if scheduling.conflicts(store.bookings(), start.isoformat(), hours, c["address"]):
                slots = scheduling.suggest_slots(store.bookings(), hours, c["address"], now=now)
                if not slots:
                    continue
                start = scheduling.parse_time(slots[0]["start"])
            booking = scheduling.new_booking(c["id"], c["name"], c["phone"].lstrip("+"), c["address"], start.isoformat(),
                                             hours, c["booking"])
            store.save_booking(booking)
            store.add_audit(c["id"], "owner", "schedule",
                            f"Booked {scheduling.describe_when(booking['start'])} ({hours:g} hours on site)")
            booked += 1
    return {"customers": made, "bookings": booked,
            "days": sum(len(views.booking_days_view(b)) for b in store.bookings() if b["user_id"].startswith("demo-"))}
