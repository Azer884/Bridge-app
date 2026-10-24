"""The owner's side: push notifications, an approved estimate re-priced when the customer changes the job, jobs split
over working days, and the demo data."""
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from src import scheduling, views
from src.events import IncomingEvent
from src.push import PushNotifier
from src.server import create_app
from src.service import IncomingService
from src.store import SqliteStore
from tests.test_core import FakeClient, reply
from tests.test_malay_orders_voice import FULL, job_state

TZ = scheduling.TZ
KEY = {"x-api-key": "key"}
TOKEN = "ExponentPushToken[abcdefghijklmnop]"


def service_with_alerts():
    directory = tempfile.TemporaryDirectory()
    alerts = []
    service = IncomingService(SqliteStore(Path(directory.name) / "t.db"), FULL, FakeClient(reply("x?")),
                              notify=lambda title, body, data: alerts.append((title, body, data)))
    service._dir = directory
    return service, alerts


def approved(service):
    state = job_state()
    state.stage, state.contact_confirmed = "done", True
    service.store.save(state)
    service.handle(IncomingEvent("m0", "u", text="ok"))        # priced
    service.approve_quote("u", lambda text: True)
    return service.store.load("u")


class RepriceAfterApprovalTests(unittest.TestCase):
    def test_a_changed_job_goes_back_for_approval_at_the_new_price(self):
        service, alerts = service_with_alerts()
        before = approved(service)
        self.assertEqual(before.quote_status, "approved")
        out = service.handle(IncomingEvent("m1", "u", text="actually I want premium paint instead"))
        state = service.store.load("u")
        self.assertEqual(state.verified["paint_tier"], "premium")
        self.assertEqual(state.quote_status, "pending_approval")              # the approve button is back
        self.assertGreater(state.quote["total"], before.quote["total"])
        self.assertEqual(state.quote["previous_total"], before.quote["approved_total"])
        self.assertIn("updated estimate", out[0])
        self.assertEqual(alerts[-1][0], "Changed job: approve the new price")
        sent = []
        service.approve_quote("u", lambda text: sent.append(text) or True)
        self.assertIn("updated", sent[0])

    def test_one_more_room_after_approval_is_priced_too(self):
        service, _ = service_with_alerts()
        before = approved(service)
        service.handle(IncomingEvent("m1", "u", text="can you also do the kitchen 3x3x2.5?"))
        state = service.store.load("u")
        self.assertEqual(len(state.verified.get("extra_rooms", [])), 1)
        self.assertEqual(state.quote_status, "pending_approval")
        self.assertGreater(state.quote["total"], before.quote["total"])


class AlertTests(unittest.TestCase):
    def test_new_estimate_and_a_person_asked_for(self):
        service, alerts = service_with_alerts()
        state = job_state()
        state.stage, state.contact_confirmed = "done", True
        service.store.save(state)
        service.handle(IncomingEvent("m0", "u", text="ok"))
        self.assertEqual(alerts[-1][0], "Estimate to approve")
        self.assertEqual(alerts[-1][2]["user_id"], "u")
        count = len(alerts)
        service.handle(IncomingEvent("m1", "u", text="ok"))
        self.assertEqual(len(alerts), count)                                  # nothing new: no second alert

    def test_push_tokens_and_sending(self):
        directory = tempfile.TemporaryDirectory()
        store = SqliteStore(Path(directory.name) / "t.db")
        posted = []
        push = PushNotifier(store, post=lambda url, payload, headers: posted.append(payload) or {
            "data": [{"status": "error", "details": {"error": "DeviceNotRegistered"}}]})
        with self.assertRaises(ValueError):
            push.register("not a token")
        push.register(TOKEN, "android")
        push.notify("Hello", "Body", {"user_id": "u"}, wait=True)
        self.assertEqual(posted[0][0]["to"], TOKEN)
        self.assertEqual(push.tokens(), [])                                   # the app was removed from that phone
        directory.cleanup()

    def test_register_route(self):
        directory = tempfile.TemporaryDirectory()
        service = IncomingService(SqliteStore(Path(directory.name) / "t.db"), FULL, None)
        api = TestClient(create_app(service, None, {"INCOMING_API_KEY": "key", "MESSAGE_WINDOW_SECONDS": "0"}))
        self.assertEqual(api.post("/api/push/register", json={"token": TOKEN}).status_code, 401)
        self.assertEqual(api.post("/api/push/register", headers=KEY, json={"token": TOKEN}).json()["devices"], 1)
        self.assertEqual(api.post("/api/push/register", headers=KEY, json={"token": "x"}).status_code, 422)
        self.assertIsNotNone(service.notify)


class WorkingDayTests(unittest.TestCase):
    def test_never_more_than_eight_hours_a_day_with_lunch_free(self):
        monday = datetime(2026, 10, 26, 9, 0, tzinfo=TZ)
        segments = scheduling.day_segments(monday, 20)
        days = scheduling.working_days(segments)
        for start, end in segments:
            self.assertFalse(start.hour < 14 and end.hour > 13 and end.minute + end.hour * 60 > 13 * 60 and start.hour < 13
                             and end > start.replace(hour=13, minute=0))     # no block runs through lunch
        per_day = {}
        for start, end in segments:
            per_day[start.date()] = per_day.get(start.date(), 0) + (end - start).total_seconds() / 3600
        self.assertTrue(all(h <= 8 for h in per_day.values()))
        self.assertEqual(len(days), 3)                                       # 8 + 8 + 4
        self.assertEqual(scheduling.work_windows(datetime(2026, 10, 31).date())[-1][1].hour, 13)   # Saturday half day
        self.assertEqual(scheduling.work_windows(datetime(2026, 11, 1).date()), [])               # Sunday off

    def test_a_long_booking_shows_one_entry_per_day(self):
        booking = scheduling.new_booking("u", "Siti", "", "x", datetime(2026, 10, 26, 9, 0, tzinfo=TZ).isoformat(), 20,
                                         "confirmed")
        pieces = views.booking_days_view(booking)
        self.assertEqual([p["id"] for p in pieces], [booking["id"], booking["id"] + "~d2", booking["id"] + "~d3"])
        self.assertEqual(pieces[1]["customer"], "Siti (day 2 of 3)")


class DemoTests(unittest.TestCase):
    def test_seed_and_clear(self):
        directory = tempfile.TemporaryDirectory()
        service = IncomingService(SqliteStore(Path(directory.name) / "t.db"), FULL, None)
        now = datetime(2026, 10, 25, 10, 0, tzinfo=TZ)
        result = service.seed_demo(now)
        self.assertGreaterEqual(result["customers"], 6)
        self.assertGreaterEqual(result["bookings"], 4)
        self.assertGreater(result["days"], result["bookings"])               # the big job runs over several days
        statuses = {views.front_status(s) for s in service.store.conversations()}
        self.assertTrue({"approved", "pending_approval", "needs_inspection"} <= statuses)
        self.assertTrue(service.booking_list())
        again = service.seed_demo(now)
        self.assertEqual(again["customers"], result["customers"])            # replaced, not doubled
        self.assertEqual(service.clear_demo(), result["customers"])
        self.assertEqual(service.store.bookings(), [])
        directory.cleanup()


if __name__ == "__main__":
    unittest.main()


class EstimateMessageTests(unittest.TestCase):
    def test_bullets_and_the_pdf(self):
        service, _ = service_with_alerts()
        state = job_state()
        state.stage, state.contact_confirmed = "done", True
        service.store.save(state)
        service.handle(IncomingEvent("m0", "u", text="ok"))
        texts, files = [], []
        service.approve_quote("u", lambda text: texts.append(text) or True,
                              send_pdf=lambda data, name: files.append((data, name)) or True)
        self.assertIn("• Estimate: MYR", texts[0])
        self.assertIn("• Room: 4 x 3 x 2.5 m", texts[0])
        self.assertIn("attached as a PDF", texts[0])
        self.assertTrue(files[0][0].startswith(b"%PDF"))
        self.assertTrue(files[0][1].endswith(".pdf"))


class InspectionApprovalTests(unittest.TestCase):
    def test_a_job_flagged_for_inspection_can_still_be_approved(self):
        service, _ = service_with_alerts()
        state = job_state()
        state.stage, state.contact_confirmed = "done", True
        state.verified["surface_condition"] = "damp and mould everywhere"
        service.store.save(state)
        service.handle(IncomingEvent("m0", "u", text="ok"))
        self.assertEqual(service.store.load("u").quote_status, "needs_inspection")
        sent = []
        self.assertTrue(service.approve_quote("u", lambda text: sent.append(text) or True))
        state = service.store.load("u")
        self.assertEqual(state.quote_status, "approved")
        self.assertFalse(state.needs_human)
        with self.assertRaises(ValueError):
            service.approve_quote("u", lambda text: True)              # approved already: nothing is waiting
