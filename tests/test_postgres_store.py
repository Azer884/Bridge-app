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
            store = make_store({"DATABASE_PATH": os.path.join(directory, "b.db"), "DATABASE_URL": "sqlite:///x"}, "unused")
            self.assertTrue(store.path.endswith("b.db"))


@unittest.skipUnless(URL, "TEST_DATABASE_URL is not set")
class PostgresStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = PostgresStore(URL)
        with self.store._conn() as conn:
            for table in ("conversations", "processed_messages", "messages", "settings", "events"):
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
