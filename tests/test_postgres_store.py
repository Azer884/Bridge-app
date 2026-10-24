"""PostgresStore against a real PostgreSQL. Skipped unless TEST_DATABASE_URL is set, e.g.
docker run -d -e POSTGRES_PASSWORD=test -e POSTGRES_DB=bridge -p 55432:5432 postgres:16-alpine
TEST_DATABASE_URL=postgresql://postgres:test@localhost:55432/bridge python -m unittest tests.test_postgres_store
"""
import os
import threading
import unittest

from src.conversation import ConversationState
from src.store import PostgresStore, SqliteStore, make_store

URL = os.environ.get("TEST_DATABASE_URL")


class MakeStoreTests(unittest.TestCase):
    def test_sqlite_by_default_and_postgres_for_a_postgres_url(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            store = make_store({}, os.path.join(directory, "a.db"))
            self.assertIsInstance(store, SqliteStore)
            self.assertNotIsInstance(store, PostgresStore)
            self.assertEqual(store.stats(), {"backend": "sqlite", "conversations": 0, "messages": 0, "events": 0})
            store = make_store({"DATABASE_PATH": os.path.join(directory, "b.db"), "DATABASE_URL": "sqlite:///x"}, "unused")
            self.assertTrue(store.path.endswith("b.db"))


@unittest.skipUnless(URL, "TEST_DATABASE_URL is not set")
class PostgresStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = PostgresStore(URL)
        with self.store._conn() as conn:
            for table in ("conversations", "processed_messages", "messages", "settings", "events", "bookings", "audit"):
                conn.execute(f"DELETE FROM {table}")

    def test_state_round_trip_keeps_everything(self):
        state = ConversationState("u1", lang="ms")
        state.verified = {"address": "Jalan Bunga", "surfaces": ["one wall"], "room_length_m": 4.5}
        state.orders = [{"verified": {"address": "old"}, "quote": {"total": 99.5}}]
        state.followups = [{"text": "hi", "at": 1.5}]
        self.store.save(state)
        loaded = self.store.load("u1")
        self.assertEqual(loaded.verified, state.verified)
        self.assertEqual(loaded.orders, state.orders)
        self.assertEqual(loaded.lang, "ms")
        state.stage = "done"
        self.store.save(state)                                  # upsert, not a duplicate row
        self.assertEqual([s.stage for s in self.store.conversations()], ["done"])
        self.assertEqual(self.store.load("nobody").conversation_id, "nobody")

    def test_bookings_and_audit(self):
        self.store.save_booking({"id": "b1", "user_id": "u1", "start": "2026-10-26T09:00:00+08:00", "status": "tentative"})
        self.store.save_booking({"id": "b1", "user_id": "u1", "start": "2026-10-26T09:00:00+08:00", "status": "confirmed"})
        self.store.save_booking({"id": "b2", "user_id": "u2", "start": "2026-10-25T09:00:00+08:00", "status": "confirmed"})
        self.assertEqual([b["id"] for b in self.store.bookings()], ["b2", "b1"])             # by start time
        self.assertEqual(self.store.get_booking("b1")["status"], "confirmed")
        self.assertTrue(self.store.delete_booking("b2"))
        self.assertFalse(self.store.delete_booking("b2"))
        first = self.store.add_audit("u1", "ai", "ai_extraction", "read the job")
        second = self.store.add_audit("u1", "owner", "override", "changed length", [{"field": "length_m", "from": "4", "to": "5"}])
        self.assertEqual((first["seq"], second["seq"]), (1, 2))
        self.assertNotEqual(first["hash"], second["hash"])
        self.assertEqual([e["seq"] for e in self.store.audit("u1")], [2, 1])                 # newest first
        self.store.log_message("u1", "in", "photo", "777")
        message = self.store.messages("u1")[0]
        self.assertEqual((message["media_id"], message["direction"]), ("777", "in"))
        self.assertGreater(message["ts"], 1e9)

    def test_stats_report_the_backend(self):
        self.store.save(ConversationState("u1"))
        stats = self.store.stats()
        self.assertEqual((stats["backend"], stats["conversations"]), ("postgres", 1))

    def test_message_ids_are_claimed_once_and_can_be_released(self):
        self.assertTrue(self.store.claim_message("m1", "u1"))
        self.assertFalse(self.store.claim_message("m1", "u1"))
        self.store.release_message("m1")
        self.assertTrue(self.store.claim_message("m1", "u1"))

    def test_only_one_of_many_racing_deliveries_wins(self):
        wins = []
        threads = [threading.Thread(target=lambda: wins.append(self.store.claim_message("race", "u"))) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sum(wins), 1)

    def test_settings_messages_and_events(self):
        self.assertIsNone(self.store.get_setting("active_persona"))
        self.store.set_setting("active_persona", "ben")
        self.store.set_setting("active_persona", "mei")
        self.assertEqual(self.store.get_setting("active_persona"), "mei")
        self.store.set_setting("personas", {"x": {"name": "Zoe"}})
        self.assertEqual(self.store.get_setting("personas"), {"x": {"name": "Zoe"}})
        self.store.log_message("u1", "in", "hello")
        self.store.log_message("u1", "out", "hi", "77")
        self.assertEqual([m["text"] for m in self.store.messages("u1")], ["hello", "hi"])
        for i in range(520):
            self.store.log_event("webhook", f"event {i}")
        events = self.store.events(5)
        self.assertEqual(events[0]["detail"], "event 519")        # newest first
        with self.store._conn() as conn:
            self.assertLessEqual(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0], 501)

    def test_a_full_conversation_runs_on_postgres(self):
        import json
        from pathlib import Path
        from src.events import IncomingEvent
        from src.service import IncomingService
        from tests.test_core import FakeClient, reply
        config = json.loads(Path("config/business_config.example.json").read_text(encoding="utf-8"))
        service = IncomingService(self.store, config, FakeClient(reply("Which surfaces would you like painted?")))
        out = service.handle(IncomingEvent("w1", "6012", text="hi, saya nak cat dinding bilik", profile_name="Azer"))
        self.assertTrue(out)
        state = self.store.load("6012")
        self.assertEqual(state.lang, "ms")
        self.assertEqual(self.store.messages("6012")[0]["text"], "hi, saya nak cat dinding bilik")
        restarted = IncomingService(PostgresStore(URL), config, FakeClient())     # a republish: new process, same data
        self.assertEqual(restarted.store.load("6012").lang, "ms")
        self.assertEqual(restarted.customers()[0]["user_id"], "6012")


if __name__ == "__main__":
    unittest.main()
