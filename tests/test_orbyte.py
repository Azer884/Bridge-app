"""The hub link: roles on approve and reject, the reject path, and signed events."""
import json
import unittest

from fastapi.testclient import TestClient

from src import orbyte
from src.events import IncomingEvent
from src.server import create_app
from tests.test_server import ENV, KEY, ServiceTests, SentRecorder

UID = "60123456789"


def hub(role=None, name=None):
    headers = dict(KEY)
    if role:
        headers["x-orbyte-role"] = role
    if name:
        headers["x-orbyte-user"] = name
    return headers


class HubLinkTests(unittest.TestCase):
    def setUp(self):
        self.sender = SentRecorder()
        self.service = ServiceTests().quoting_service()
        self.service.handle(IncomingEvent("m1", UID, text="yes"))
        self.api = TestClient(create_app(self.service, self.sender, ENV))

    def audit(self):
        return [e["summary"] for e in self.service.store.audit(UID, 50)]

    def test_reviewer_cannot_approve_and_nothing_is_sent(self):
        res = self.api.post(f"/api/quotes/{UID}/approve", json={}, headers=hub("reviewer", "Mei"))
        self.assertEqual(res.status_code, 403)
        self.assertEqual(self.sender.sent, [])
        self.assertEqual(self.service.store.load(UID).quote_status, "pending_approval")

    def test_unknown_role_is_treated_as_reviewer(self):
        res = self.api.post(f"/api/quotes/{UID}/approve", json={}, headers=hub("root"))
        self.assertEqual(res.status_code, 403)

    def test_approver_approves_and_the_log_names_them(self):
        res = self.api.post(f"/api/quotes/{UID}/approve", json={}, headers=hub("approver", "Aisha"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(self.sender.sent), 1)
        self.assertTrue(any("approved" in s and "Aisha (approver)" in s for s in self.audit()))

    def test_no_role_header_keeps_working_as_admin(self):
        self.assertEqual(self.api.post(f"/api/quotes/{UID}/approve", json={}, headers=KEY).status_code, 200)

    def test_reject_blocks_the_send_and_is_recorded(self):
        res = self.api.post(f"/api/quotes/{UID}/reject", json={"reason": "price too low"}, headers=hub("approver", "Aisha"))
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["notified"])
        self.assertEqual(self.service.store.load(UID).quote_status, "rejected")
        self.assertTrue(any("rejected: price too low" in s for s in self.audit()))
        # the customer is told, with the owner's reason and no price
        self.assertEqual(len(self.sender.sent), 1)
        told = str(self.sender.sent[0])
        self.assertIn("can't give you an estimate", told)
        self.assertIn("price too low", told)
        self.assertNotIn("RM", told)
        self.assertTrue(any("The customer was told" in s for s in self.audit()))
        # a rejected estimate cannot be approved by mistake
        self.assertEqual(self.api.post(f"/api/quotes/{UID}/approve", json={}, headers=KEY).status_code, 409)
        self.assertEqual(len(self.sender.sent), 1)

    def test_a_rejected_job_is_flagged_rejected_and_no_longer_needs_the_owner(self):
        state = self.service.store.load(UID)
        state.needs_human, state.attention = True, True
        self.service.store.save(state)
        self.api.post(f"/api/quotes/{UID}/reject", json={"reason": "check the height"}, headers=KEY)
        state = self.service.store.load(UID)
        self.assertFalse(state.needs_human or state.attention)
        item = self.api.get(f"/api/quotes/{UID}", headers=KEY).json()
        self.assertEqual(item["status"], "rejected")
        self.assertEqual(item["stage"], "rejected")

    def test_reject_needs_a_reason_and_the_right_role(self):
        self.assertEqual(self.api.post(f"/api/quotes/{UID}/reject", json={}, headers=KEY).status_code, 422)
        self.assertEqual(self.api.post(f"/api/quotes/{UID}/reject", json={"reason": "no"}, headers=KEY).status_code, 422)
        self.assertEqual(self.api.post(f"/api/quotes/{UID}/reject", json={"reason": "too high"},
                                       headers=hub("reviewer")).status_code, 403)
        self.assertEqual(self.service.store.load(UID).quote_status, "pending_approval")

    def test_rejected_leaves_the_queue_and_editing_brings_it_back(self):
        self.api.post(f"/api/quotes/{UID}/reject", json={"reason": "check the height"}, headers=KEY)
        queue = self.api.get("/api/quotes?status=pending_approval", headers=KEY).json()["quotes"]
        self.assertEqual(queue, [])
        detail = self.api.get(f"/api/quotes/{UID}", headers=KEY).json()
        params = dict(detail["params"]["current"])
        params["height_m"] = 2.7
        self.api.put(f"/api/quotes/{UID}/params", json={"params": params}, headers=KEY)
        self.assertEqual(self.service.store.load(UID).quote_status, "pending_approval")

    def test_approve_requires_a_key(self):
        self.assertEqual(self.api.post(f"/api/quotes/{UID}/approve", json={}).status_code, 401)


class EmitterTests(unittest.TestCase):
    def test_events_are_signed_and_delivered(self):
        sent = []
        emitter = orbyte.Emitter("http://hub.invalid/hook", "secret", post=lambda raw, headers: sent.append((raw, headers)))
        emitter.emit("quote.approved", {"user_id": "u1"})
        for _ in range(50):
            if sent:
                break
            import time
            time.sleep(0.05)
        raw, headers = sent[0]
        self.assertEqual(json.loads(raw)["type"], "quote.approved")
        self.assertEqual(headers["x-orbyte-signature"], orbyte.sign("secret", raw))

    def test_no_url_means_no_thread_and_no_events(self):
        emitter = orbyte.Emitter("", "secret")
        emitter.emit("quote.approved", {})
        self.assertTrue(emitter.queue.empty())




class DurableOutboxTests(unittest.TestCase):
    def store(self):
        import tempfile
        from pathlib import Path
        from src.store import SqliteStore
        self.dir = tempfile.TemporaryDirectory()
        return SqliteStore(Path(self.dir.name) / "t.db")

    def test_a_delivered_event_leaves_the_outbox(self):
        import time
        store, sent = self.store(), []
        emitter = orbyte.Emitter("http://hub.invalid/hook", "s", store, post=lambda raw, headers: sent.append(raw))
        emitter.emit("quote.approved", {"user_id": "u1"})
        for _ in range(60):
            if sent and not emitter.pending():
                break
            time.sleep(0.05)
        self.assertEqual(len(sent), 1)
        self.assertEqual(emitter.pending(), [])

    def test_an_undelivered_event_survives_a_restart_and_is_sent_then(self):
        import time
        store = self.store()
        orbyte.Emitter.RETRIES = (0,)
        try:
            def down(raw, headers):
                raise OSError("hub is down")
            first = orbyte.Emitter("http://hub.invalid/hook", "s", store, post=down)
            first.emit("quote.rejected", {"user_id": "u2"})
            for _ in range(60):
                if store.events(3):
                    break
                time.sleep(0.05)
            self.assertEqual(len(first.pending()), 1)                       # still queued after the failure
            sent = []
            second = orbyte.Emitter("http://hub.invalid/hook", "s", store, post=lambda raw, headers: sent.append(raw))
            for _ in range(60):
                if sent:
                    break
                time.sleep(0.05)
            self.assertEqual(json.loads(sent[0])["type"], "quote.rejected")
            for _ in range(60):
                if not second.pending():
                    break
                time.sleep(0.05)
            self.assertEqual(second.pending(), [])
        finally:
            orbyte.Emitter.RETRIES = (0, 2, 10)


class EmbedTests(unittest.TestCase):
    def app(self, **extra):
        service = ServiceTests().quoting_service()
        return TestClient(create_app(service, SentRecorder(), {**ENV, **extra}))

    def test_only_the_hub_may_frame_the_dashboard(self):
        res = self.app(ORBYTE_ORIGIN="https://hub.example.com/").get("/health")
        self.assertEqual(res.headers["content-security-policy"], "frame-ancestors 'self' https://hub.example.com")
        self.assertNotIn("content-security-policy", self.app().get("/health").headers)

    def test_the_login_cookie_works_inside_the_hub_only_over_https(self):
        form = {"password": "pw"}
        env = {"DASHBOARD_PASSWORD": "pw", "SESSION_SECRET": "s", "ORBYTE_ORIGIN": "https://hub.example.com"}
        secure = self.app(**env).post("/login", data=form, headers={"x-forwarded-proto": "https"}, follow_redirects=False)
        self.assertIn("samesite=none", secure.headers["set-cookie"].lower())
        plain = self.app(**env).post("/login", data=form, follow_redirects=False)
        self.assertIn("samesite=lax", plain.headers["set-cookie"].lower())          # none needs https, so http stays lax


class RejectedStageTests(unittest.TestCase):
    def test_a_rejected_job_has_its_own_stage(self):
        service = ServiceTests().quoting_service()
        service.handle(IncomingEvent("m1", UID, text="yes"))
        service.reject_quote(UID, "check the height")
        self.assertEqual(service.pipeline()[0]["stage"], "rejected")


if __name__ == "__main__":
    unittest.main()
