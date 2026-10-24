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
        self.assertEqual([(s.day, s.hour, e.hour) for s, e in segments], [(31, 15, 18), (2, 9, 18)])  # Sunday skipped

    def test_same_area_job_is_slotted_right_after_its_neighbour(self):
        day = monday()
        existing = [scheduling.new_booking("a", "Siti", "", "1 Jalan A, 43900 Sepang", iso(day, 9), 4, "confirmed"),
                    scheduling.new_booking("b", "Ravi", "", "5 Jalan Z, 50450 Kuala Lumpur", iso(day + timedelta(days=1), 9),
                                           4, "confirmed")]
        slots = scheduling.suggest_slots(existing, 3, "Jalan Sunsuria, 43900 Sepang", now=day - timedelta(days=1), limit=3)
        self.assertEqual(slots[0]["reason"], "Right after Siti, same postcode")
        self.assertEqual(slots[0]["start"], iso(day, 13, 30))                    # 9 + 4h + 15 min travel gap, on the half hour
        self.assertEqual(slots[0]["score"], 100)
        self.assertTrue(all(slots[i]["score"] >= slots[i + 1]["score"] for i in range(len(slots) - 1)))

    def test_far_jobs_are_not_clustered_and_clashes_are_refused(self):
        day = monday()
        far = [scheduling.new_booking("b", "Ravi", "", "5 Jalan Z, 50450 Kuala Lumpur", iso(day, 9), 4, "confirmed")]
        slots = scheduling.suggest_slots(far, 3, "Jalan Sunsuria, 43900 Sepang", now=day - timedelta(days=1), limit=2)
        self.assertEqual(slots[0]["reason"], "Earliest free time")
        self.assertTrue(scheduling.conflicts(far, iso(day, 10), 2, "x"))          # inside Ravi's job
        self.assertTrue(scheduling.conflicts(far, iso(day, 13, 10), 2, "x"))      # too soon: travel gap of 45 minutes
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
        self.assertEqual([e["type"] for e in detail["audit"]], ["ai_extraction", "calculation"])
        self.assertEqual([e["seq"] for e in detail["audit"]], [1, 2])
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
        self.assertIn("We expect the work to take about", sent[0])
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
        self.assertIn("Kami menjangka kerja ini mengambil masa kira-kira", sent[0])


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
        moved = self.api.patch(f"/api/bookings/{booking['id']}", headers=KEY, json={"start": iso(self.day, 13)}).json()
        self.assertEqual(moved["start"], iso(self.day, 13))
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
        add_customer(self.service, "u3", "Lee", "88 Jalan Sunsuria, 43900 Sepang")
        slots = self.api.post("/api/quotes/u3/slots", headers=KEY, json={"busy": []}).json()["slots"]
        self.assertTrue(slots)
        self.assertTrue(slots[0]["reason"].startswith("Right after Azer"))
        self.assertGreaterEqual(slots[0]["score"], slots[-1]["score"])


if __name__ == "__main__":
    unittest.main()
