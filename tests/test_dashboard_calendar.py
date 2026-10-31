"""The dashboard API (the frontend's contract), the calendar, area-aware scheduling and the duration message."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from src import scheduling
from src.calendar_scheduler import TZ
from src.conversation import ConversationState
from src.events import IncomingEvent
from src.server import create_app
from src.service import IncomingService
from src.store import SqliteStore
from tests.test_core import FakeClient

FULL = json.loads(Path("config/business_config.example.json").read_text(encoding="utf-8"))
FULL.pop("privacy", None)          # the PDPA consent step has its own tests (test_consent.py)
ENV = {"INCOMING_API_KEY": "key", "MESSAGE_WINDOW_SECONDS": "0"}
KEY = {"x-api-key": "key"}


def monday():
    """A future Monday 08:00, so 'now' never falls inside the booking tests' windows."""
    day = datetime.now(TZ).replace(hour=8, minute=0, second=0, microsecond=0) + timedelta(days=7)
    return day - timedelta(days=day.weekday())


def iso(day, hour, minute=0):
    return (day + timedelta(hours=hour - 8, minutes=minute)).isoformat()


class Sender:
    last_error = ""

    def __init__(self):
        self.sent = []

    def send_text(self, to, text):
        self.sent.append((to, text))
        return True

    def fetch_media(self, media_id):
        return b"jpeg-bytes", "image/jpeg"


def priced_service(user="u1", name="Azer", address="12 Jalan Bunga, 43900 Sepang", extra=None):
    directory = tempfile.TemporaryDirectory()
    service = IncomingService(SqliteStore(Path(directory.name) / "t.db"), FULL, FakeClient())
    service._dir = directory
    add_customer(service, user, name, address, extra)
    return service


def add_customer(service, user, name, address, extra=None):
    state = ConversationState(user, lang="en")
    state.channel = {"name": name, "phone": "+60123" + user[-4:].rjust(4, "0")}
    state.greeted = state.service_checked = state.contact_confirmed = True
    state.verified.update({"surfaces": ["walls"], "room_length_m": 4.0, "room_width_m": 3.0, "room_height_m": 2.5,
                           "surface_condition": "good", "paint_tier": "standard", "colour": "white",
                           "preferred_datetime": "Friday", "address": address, "customer_name": name,
                           "phone": state.channel["phone"]})
    state.verified.update(extra or {})
    state.stage = "done"
    service.store.save(state)
    service.store.log_message(user, "in", "hello")
    service.store.log_message(user, "in", "see this", "777")
    service.store.log_message(user, "out", "Thanks for the photo")
    service.handle(IncomingEvent(f"m-{user}", user, text="ok"))          # the first message after the chat prices it
    return service.store.load(user)


class SchedulingTests(unittest.TestCase):
    def test_area_and_closeness(self):
        a = scheduling.area_of("12 Jalan Sunsuria, 43900 Sepang")
        self.assertEqual((a["postcode"], a["prefix"], a["name"]), ("43900", "439", "sepang"))
        self.assertEqual(scheduling.closeness(a, scheduling.area_of("3 Jalan B, 43900 Sepang")), "same")
        self.assertEqual(scheduling.closeness(a, scheduling.area_of("9 Jalan C, 43950 Sepang")), "near")
        self.assertEqual(scheduling.closeness(a, scheduling.area_of("1 Jalan D, 50450 Kuala Lumpur")), "far")
        self.assertEqual(scheduling.closeness(a, {}), "far")
        self.assertEqual(scheduling.area_of("somewhere"), {})

    def test_a_long_job_continues_on_the_next_working_day(self):
        start = datetime(2026, 10, 31, 15, 0, tzinfo=TZ)                         # a Saturday afternoon
        segments = scheduling.day_segments(start, 12)
        # Saturday closes at 13:00 and Sunday is off; each day is 9-13 and 14-18 with lunch kept free, 8 hours at most
        self.assertEqual([(s.day, s.hour, e.hour) for s, e in segments], [(2, 9, 13), (2, 14, 18), (3, 9, 13)])
        self.assertEqual(scheduling.working_days(segments)[0][1].hour, 18)

    def test_same_area_job_is_slotted_right_after_its_neighbour(self):
        day = monday()
        existing = [scheduling.new_booking("a", "Siti", "", "1 Jalan A, 43900 Sepang", iso(day, 9), 4, "confirmed"),
                    scheduling.new_booking("b", "Ravi", "", "5 Jalan Z, 50450 Kuala Lumpur", iso(day + timedelta(days=1), 9),
                                           4, "confirmed")]
        slots = scheduling.suggest_slots(existing, 3, "Jalan Sunsuria, 43900 Sepang", now=day - timedelta(days=1), limit=3)
        self.assertEqual(slots[0]["reason"], "Right after Siti, same postcode")
        self.assertEqual(slots[0]["start"], iso(day, 14))                        # 9 + 4h + 15 min travel gap, after lunch
        self.assertEqual(slots[0]["score"], 100)
        self.assertTrue(all(slots[i]["score"] >= slots[i + 1]["score"] for i in range(len(slots) - 1)))

    def test_far_jobs_are_not_clustered_and_clashes_are_refused(self):
        day = monday()
        far = [scheduling.new_booking("b", "Ravi", "", "5 Jalan Z, 50450 Kuala Lumpur", iso(day, 9), 4, "confirmed")]
        slots = scheduling.suggest_slots(far, 3, "Jalan Sunsuria, 43900 Sepang", now=day - timedelta(days=1), limit=2)
        self.assertEqual(slots[0]["reason"], "Earliest free time")
        self.assertTrue(scheduling.conflicts(far, iso(day, 10), 2, "x"))          # inside Ravi's job
        self.assertFalse(scheduling.conflicts(far, iso(day, 13, 10), 2, "x"))     # starts after lunch, past the 45 minute gap
        later = [scheduling.new_booking("c", "Ravi", "", "5 Jalan Z, 50450 Kuala Lumpur", iso(day, 14), 2, "confirmed")]
        self.assertTrue(scheduling.conflicts(later, iso(day, 16, 30), 1, "x"))    # too soon: travel gap of 45 minutes
        self.assertFalse(scheduling.conflicts(far, iso(day, 14), 2, "x"))
        far[0]["status"] = "cancelled"
        self.assertFalse(scheduling.conflicts(far, iso(day, 10), 2, "x"))

    def test_outside_events_block_slots(self):
        day = monday()
        busy = [(iso(day, 9), iso(day, 18))]
        slots = scheduling.suggest_slots([], 3, "", now=day - timedelta(days=1), extra_busy=busy, limit=1)
        self.assertEqual(slots[0]["start"], iso(day + timedelta(days=1), 9))


class QuoteApiTests(unittest.TestCase):
    def setUp(self):
        self.service = priced_service()
        self.sender = Sender()
        self.api = TestClient(create_app(self.service, self.sender, ENV))

    def test_list_items_match_the_frontend_types(self):
        (item,) = self.api.get("/api/quotes", headers=KEY).json()["quotes"]
        self.assertEqual((item["customer"], item["status"], item["stage"]), ("Azer", "pending_approval", "requires_approval"))
        self.assertEqual(item["job"]["surfaces"], "walls")
        self.assertEqual(item["job"]["name"], "Azer")
        self.assertGreater(item["quote"]["labor_hours"], 0)
        self.assertEqual(self.api.get("/api/quotes?status=collecting", headers=KEY).json()["quotes"], [])

    def test_detail_has_params_chat_photos_and_audit(self):
        detail = self.api.get("/api/quotes/u1", headers=KEY).json()
        self.assertEqual(detail["params"]["kind"], "painting")
        keys = [f["key"] for f in detail["params"]["schema"]]
        self.assertEqual(keys, ["length_m", "width_m", "height_m", "surface_condition", "coats", "tier"])
        self.assertEqual(detail["params"]["ai"]["length_m"], 4.0)
        self.assertEqual(detail["params"]["current"], detail["params"]["ai"])
        self.assertEqual([m["role"] for m in detail["chat"]][:3], ["customer", "customer", "assistant"])
        self.assertEqual(detail["photos"][0]["url"], "/api/media/777")
        self.assertEqual([e["type"] for e in detail["audit"]], ["state_change", "ai_extraction", "calculation"])
        self.assertEqual([e["seq"] for e in detail["audit"]], [1, 2, 3])
        self.assertGreater(detail["duration_hours"], 0)
        self.assertFalse(detail["locked"])
        self.assertEqual(self.api.get("/api/quotes/nobody", headers=KEY).status_code, 404)
        self.assertEqual(self.api.get("/api/quotes/u1").status_code, 401)

    def test_one_wall_has_no_width_field(self):
        service = priced_service("u2", "Sam", extra={"surfaces": ["one wall"]})
        fields = [f["key"] for f in service.detail("u2")["params"]["schema"]]
        self.assertNotIn("width_m", fields)

    def test_recalculate_does_not_save_but_save_params_does(self):
        before = self.api.get("/api/quotes/u1", headers=KEY).json()["quote"]["total"]
        params = {"length_m": 8.0, "width_m": 6.0, "height_m": 2.5, "surface_condition": "poor", "coats": 3,
                  "tier": "premium"}
        recalculated = self.api.post("/api/quotes/u1/recalculate", headers=KEY, json={"params": params}).json()
        self.assertGreater(recalculated["quote"]["total"], before)
        self.assertGreater(recalculated["duration_hours"], 0)
        self.assertEqual(self.api.get("/api/quotes/u1", headers=KEY).json()["quote"]["total"], before)
        saved = self.api.put("/api/quotes/u1/params", headers=KEY, json={"params": params}).json()
        self.assertEqual(saved["quote"]["total"], recalculated["quote"]["total"])
        self.assertEqual(saved["params"]["current"]["length_m"], 8.0)
        self.assertEqual(saved["params"]["ai"]["length_m"], 4.0)                 # what the assistant read never changes
        override = [e for e in saved["audit"] if e["type"] == "override"][0]
        self.assertIn("length_m", [c["field"] for c in override["changes"]])
        self.assertEqual(override["actor"], "owner")

    def test_values_lock_once_the_estimate_is_sent(self):
        self.assertEqual(self.api.post("/api/quotes/u1/approve", headers=KEY).status_code, 200)
        detail = self.api.get("/api/quotes/u1", headers=KEY).json()
        self.assertTrue(detail["locked"])
        self.assertEqual(detail["stage"], "quote_sent")
        self.assertEqual(self.api.put("/api/quotes/u1/params", headers=KEY, json={"params": {"coats": 3}}).status_code, 409)

    def test_invalid_json_body_is_422(self):
        self.assertEqual(self.api.post("/api/quotes/u1/recalculate", headers=KEY, json={}).status_code, 422)

    def test_pdf_is_the_customers_estimate_without_a_breakdown(self):
        import base64
        params = {"length_m": 4.0, "width_m": 3.0, "height_m": 2.5, "surface_condition": "good", "coats": 2,
                  "tier": "standard"}
        body = self.api.post("/api/quotes/u1/pdf", headers=KEY, json={"params": params}).json()
        data = base64.b64decode(body["base64"])
        self.assertTrue(data.startswith(b"%PDF-1.4"))
        self.assertIn(b"Estimated total: MYR", data)
        self.assertNotIn(b"Labour", data)
        self.assertEqual(body["filename"], "estimate-u1.pdf")

    def test_pipeline_audit_media_and_whatsapp(self):
        rows = self.api.get("/api/pipeline", headers=KEY).json()["quotes"]
        self.assertEqual([r["stage"] for r in rows], ["requires_approval"])
        entries = self.api.get("/api/audit?limit=5", headers=KEY).json()["entries"]
        self.assertEqual(entries[0]["customer"], "Azer")
        self.assertEqual(self.api.get("/api/media/777", headers=KEY).content, b"jpeg-bytes")
        self.assertEqual(self.api.get("/api/whatsapp/status", headers=KEY).json(), {"number": None, "status": "linked"})
        self.assertEqual(self.api.post("/api/whatsapp/link", headers=KEY, json={"number": "+60123456789"}).json()["number"],
                         "+60123456789")
        self.assertEqual(self.api.delete("/api/whatsapp/link", headers=KEY).status_code, 204)
        self.assertIsNone(self.api.get("/api/whatsapp/status", headers=KEY).json()["number"])

    def test_cors_only_for_listed_origins(self):
        api = TestClient(create_app(self.service, self.sender, {**ENV, "CORS_ORIGINS": "https://dash.example"}))
        ok = api.options("/api/quotes", headers={"Origin": "https://dash.example", "Access-Control-Request-Method": "GET",
                                                 "Access-Control-Request-Headers": "x-api-key"})
        self.assertEqual(ok.headers.get("access-control-allow-origin"), "https://dash.example")
        other = api.options("/api/quotes", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
        self.assertNotIn("access-control-allow-origin", other.headers)
        self.assertNotIn("access-control-allow-origin", self.api.options("/api/quotes", headers={
            "Origin": "https://dash.example", "Access-Control-Request-Method": "GET"}).headers)


class DurationMessageTests(unittest.TestCase):
    def test_the_estimate_message_tells_the_customer_how_long_it_takes(self):
        service = priced_service()
        sent = []
        service.approve_quote("u1", lambda text: sent.append(text) or True)
        self.assertIn("Time needed: about", sent[0])
        self.assertIn("hours on site with a team of 2", sent[0])
        self.assertIn("estimate", sent[0])
        self.assertNotIn("Labour", sent[0])

    def test_in_malay(self):
        service = priced_service()
        state = service.store.load("u1")
        state.lang = "ms"
        service.store.save(state)
        sent = []
        service.approve_quote("u1", lambda text: sent.append(text) or True)
        self.assertIn("Tempoh kerja: kira-kira", sent[0])


class BookingFlowTests(unittest.TestCase):
    def setUp(self):
        self.service = priced_service()
        self.sender = Sender()
        self.api = TestClient(create_app(self.service, self.sender, ENV))
        self.day = monday()

    def offer(self, hour=9):
        res = self.api.post("/api/bookings", headers=KEY, json={
            "user_id": "u1", "customer": "Azer", "address": "x", "start": iso(self.day, hour), "end": iso(self.day, hour + 3)})
        return res

    def test_offer_confirm_by_customer_reply(self):
        res = self.offer()
        self.assertEqual(res.status_code, 200)
        booking = res.json()
        self.assertEqual((booking["status"], booking["notified"]), ("tentative", True))
        self.assertIn("Does that work for you?", self.sender.sent[-1][1])
        self.assertIn("hours on site", self.sender.sent[-1][1])
        self.assertIsNotNone(self.service.store.load("u1").pending_booking)
        reply = self.service.handle(IncomingEvent("y1", "u1", text="yes please"))[0]
        self.assertIn("you're booked in", reply)
        self.assertEqual(self.service.store.get_booking(booking["id"])["status"], "confirmed")
        self.assertIsNone(self.service.store.load("u1").pending_booking)
        self.assertEqual(self.api.get("/api/quotes/u1", headers=KEY).json()["audit"][-1]["type"], "schedule")

    def test_customer_says_no_or_proposes_another_day(self):
        booking = self.offer().json()
        reply = self.service.handle(IncomingEvent("n1", "u1", text="no, how about next Friday?"))[0]
        self.assertIn("they'll suggest another time", reply)
        state = self.service.store.load("u1")
        self.assertTrue(state.attention)
        self.assertEqual(state.verified["preferred_datetime"], "no, how about next Friday?")
        self.assertEqual(self.service.store.get_booking(booking["id"])["status"], "cancelled")

    def test_an_unclear_reply_gets_one_reminder(self):
        self.offer()
        first = self.service.handle(IncomingEvent("c1", "u1", text="hmm what is the paint made of"))
        self.assertIn("Does", first[0])
        self.assertIn("work for you", first[0])
        self.assertTrue(self.service.store.load("u1").pending_booking["reminded"])

    def test_double_booking_is_refused(self):
        self.assertEqual(self.offer().status_code, 200)
        add_customer(self.service, "u2", "Siti", "9 Jalan Z, 50450 Kuala Lumpur")
        res = self.api.post("/api/bookings", headers=KEY, json={"user_id": "u2", "start": iso(self.day, 10), "end": iso(self.day, 12)})
        self.assertEqual(res.status_code, 409)

    def test_list_move_confirm_cancel_delete(self):
        booking = self.offer().json()
        listed = self.api.get(f"/api/bookings?from={iso(self.day, 0)}&to={iso(self.day + timedelta(days=2), 20)}", headers=KEY)
        (row,) = listed.json()["bookings"]
        self.assertEqual((row["customer"], row["status"], row["quote_status"]), ("Azer", "tentative", "pending_approval"))
        self.assertEqual(self.api.get(f"/api/bookings?from={iso(self.day + timedelta(days=30), 0)}", headers=KEY).json()["bookings"], [])
        confirmed = self.api.patch(f"/api/bookings/{booking['id']}", headers=KEY, json={"status": "confirmed"}).json()
        self.assertEqual(confirmed["status"], "confirmed")
        self.assertIn("you're booked in", self.sender.sent[-1][1])
        moved = self.api.patch(f"/api/bookings/{booking['id']}", headers=KEY, json={"start": iso(self.day, 14)}).json()
        self.assertEqual(moved["start"], iso(self.day, 14))
        self.assertIn("has moved to", self.sender.sent[-1][1])
        self.assertEqual(self.api.get("/api/quotes/u1", headers=KEY).json()["stage"], "requires_approval")
        self.service.approve_quote("u1", lambda text: True)
        self.assertEqual(self.api.get("/api/quotes/u1", headers=KEY).json()["stage"], "scheduled")
        self.assertEqual(self.api.delete(f"/api/bookings/{booking['id']}", headers=KEY).status_code, 204)
        self.assertIn("no longer available", self.sender.sent[-1][1])
        self.assertEqual(self.api.get("/api/bookings", headers=KEY).json()["bookings"], [])
        self.assertEqual(self.api.patch("/api/bookings/nope", headers=KEY, json={"status": "cancelled"}).status_code, 404)
        self.assertEqual(self.api.post("/api/bookings", json={"user_id": "u1", "start": iso(self.day, 9), "end": iso(self.day, 12)}).status_code, 401)

    def test_slots_for_a_customer_cluster_by_area(self):
        booking = self.offer().json()
        self.api.patch(f"/api/bookings/{booking['id']}", headers=KEY, json={"status": "confirmed"})
        add_customer(self.service, "u3", "Lee", "88 Jalan Sunsuria, 43900 Sepang", {"preferred_datetime": "anytime"})
        slots = self.api.post("/api/quotes/u3/slots", headers=KEY, json={"busy": []}).json()["slots"]
        self.assertTrue(slots)
        self.assertTrue(slots[0]["reason"].startswith("Right after Azer"))
        self.assertGreaterEqual(slots[0]["score"], slots[-1]["score"])


class PreferenceAndLocationTests(unittest.TestCase):
    def test_what_the_customer_said_is_understood(self):
        saturday = datetime(2026, 10, 24, 18, 0, tzinfo=TZ)
        pref = scheduling.parse_preference("Tomorrow evening", saturday)
        self.assertEqual((pref["date"].isoformat(), pref["part"]), ("2026-10-25", "evening"))
        pref = scheduling.parse_preference("monday evening please", saturday)
        self.assertEqual((pref["weekday"], pref["part"]), (0, "evening"))
        self.assertEqual(scheduling.parse_preference("tomorrow 8am", saturday)["hour"], 8)
        self.assertEqual(scheduling.parse_preference("26 Oct", saturday)["date"].isoformat(), "2026-10-26")
        self.assertEqual(scheduling.parse_preference("Isnin petang", saturday)["part"], "evening")
        empty = scheduling.parse_preference("anytime", saturday)
        self.assertFalse(any(empty[k] for k in ("date", "weekday", "part", "hour", "after")))

    def test_evening_preference_gets_an_evening_slot_not_9am(self):
        saturday = datetime(2026, 10, 24, 18, 0, tzinfo=TZ)
        pref = scheduling.parse_preference("Monday evening", saturday)
        slots = scheduling.suggest_slots([], 2.9, "x", now=saturday, preference=pref, limit=3)
        self.assertEqual(slots[0]["start"][:16], "2026-10-26T15:00")                  # ends before closing at 18:00
        self.assertIn("asked for", slots[0]["reason"])
        self.assertEqual(slots[0]["score"], 100)
        self.assertLess(slots[-1]["score"], 100)

    def test_a_sunday_request_moves_to_the_next_working_day(self):
        saturday = datetime(2026, 10, 24, 18, 0, tzinfo=TZ)
        pref = scheduling.parse_preference("tomorrow morning", saturday)               # a Sunday
        slots = scheduling.suggest_slots([], 2, "x", now=saturday, preference=pref, limit=1)
        self.assertEqual(slots[0]["start"][:16], "2026-10-26T09:00")

    def test_shared_coordinates_decide_how_close_two_jobs_are(self):
        a, b = {"lat": 2.8345, "lon": 101.7020}, {"lat": 2.8327, "lon": 101.7032}      # about 250 m apart
        far = {"lat": 3.139, "lon": 101.6869}                                           # Kuala Lumpur
        self.assertEqual(scheduling.closeness(scheduling.area_of("x", a), scheduling.area_of("y", b)), "same")
        self.assertEqual(scheduling.closeness(scheduling.area_of("x", a), scheduling.area_of("y", far)), "far")
        self.assertLess(scheduling.km_between(a, b), 1)

    def test_the_slots_endpoint_uses_the_customers_words_and_location(self):
        service = priced_service("u5", "Dee", "somewhere", {"preferred_datetime": "Monday evening", "surfaces": ["ceiling"],
                                                             "room_length_m": 3.0, "room_width_m": 3.0,
                                                             "location": {"lat": 2.83, "lon": 101.70}})
        api = TestClient(create_app(service, Sender(), ENV))
        slots = api.post("/api/quotes/u5/slots", headers=KEY, json={"busy": []}).json()["slots"]
        self.assertEqual(datetime.fromisoformat(slots[0]["start"]).weekday(), 0)
        self.assertGreaterEqual(datetime.fromisoformat(slots[0]["start"]).hour, 13)
        detail = api.get("/api/quotes/u5", headers=KEY).json()
        self.assertEqual(detail["job"]["location"]["maps_url"], "https://www.google.com/maps?q=2.83,101.7")


class HumanTakeoverTests(unittest.TestCase):
    def setUp(self):
        self.service = priced_service()
        self.sender = Sender()
        self.api = TestClient(create_app(self.service, self.sender, ENV))

    def test_owner_message_goes_out_logged_and_the_assistant_stays_quiet(self):
        state = self.service.store.load("u1")
        state.needs_human, state.attention = True, True
        self.service.store.save(state)
        res = self.api.post("/api/quotes/u1/message", headers=KEY, json={"text": "Hi Azer, Daniel here. Happy to help."})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.sender.sent[-1], ("u1", "Hi Azer, Daniel here. Happy to help."))
        detail = self.api.get("/api/quotes/u1", headers=KEY).json()
        self.assertEqual(detail["chat"][-1]["role"], "owner")
        self.assertTrue(detail["human_active"])
        self.assertFalse(detail["needs_human"])
        self.assertEqual(detail["audit"][-1]["actor"], "owner")
        replies = self.service.handle(IncomingEvent("q1", "u1", text="how long will it take?"))
        self.assertEqual(replies, [])                                                    # the owner will answer
        self.assertTrue(self.service.store.load("u1").attention)                        # and is told there is a new message
        self.assertEqual(self.api.post("/api/quotes/u1/resume", headers=KEY).status_code, 200)
        self.assertTrue(self.service.handle(IncomingEvent("q2", "u1", text="how long will it take?")))

    def test_validation_and_failures(self):
        self.assertEqual(self.api.post("/api/quotes/u1/message", headers=KEY, json={"text": ""}).status_code, 422)
        self.assertEqual(self.api.post("/api/quotes/u1/message", headers=KEY, json={"text": "x" * 1001}).status_code, 422)
        self.assertEqual(self.api.post("/api/quotes/nobody/message", headers=KEY, json={"text": "hi"}).status_code, 404)
        self.assertEqual(self.api.post("/api/quotes/u1/message", json={"text": "hi"}).status_code, 401)

        class Failing(Sender):
            def send_text(self, to, text):
                return False

        api = TestClient(create_app(self.service, Failing(), ENV))
        self.assertEqual(api.post("/api/quotes/u1/message", headers=KEY, json={"text": "hi"}).status_code, 502)
        self.assertEqual(self.service.store.load("u1").human_until, 0.0)               # nothing was sent: no takeover

    def test_a_slot_answer_still_works_during_a_takeover(self):
        booking = self.api.post("/api/bookings", headers=KEY, json={
            "user_id": "u1", "start": iso(monday(), 9), "end": iso(monday(), 12)}).json()
        self.api.post("/api/quotes/u1/message", headers=KEY, json={"text": "hello"})
        reply = self.service.handle(IncomingEvent("y9", "u1", text="yes"))[0]
        self.assertIn("you're booked in", reply)
        self.assertEqual(self.service.store.get_booking(booking["id"])["status"], "confirmed")


class NewCustomerVisibilityTests(unittest.TestCase):
    def test_a_customer_who_only_said_hello_is_in_the_pipeline_and_the_collecting_list(self):
        service = priced_service()                       # one finished customer already
        service.handle(IncomingEvent("hello-1", "60198765432", text="hi", profile_name="Team Mate"))
        api = TestClient(create_app(service, Sender(), ENV))
        rows = {r["user_id"]: r for r in api.get("/api/pipeline", headers=KEY).json()["quotes"]}
        self.assertEqual(rows["60198765432"]["stage"], "pending_extraction")
        self.assertEqual(rows["60198765432"]["customer"], "Team Mate")
        collecting = api.get("/api/quotes?status=collecting", headers=KEY).json()["quotes"]
        self.assertEqual([q["user_id"] for q in collecting], ["60198765432"])
        self.assertEqual([q["user_id"] for q in api.get("/api/quotes", headers=KEY).json()["quotes"]], ["u1"])
        service.store.log_event("send_failed", "x")
        service.store.log_event("sent", "y")
        events = api.get("/api/events", headers=KEY).json()["events"]
        self.assertEqual([(e["kind"], e["ok"]) for e in events], [("sent", True), ("send_failed", False)])
        self.assertRegex(events[0]["ts"], r"^20\d\d-\d\d-\d\dT")           # a date the dashboard can read, not epoch seconds


if __name__ == "__main__":
    unittest.main()
