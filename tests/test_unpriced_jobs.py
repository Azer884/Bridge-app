"""A finished job the engine cannot price must reach the owner, not vanish."""
import json
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from src.server import create_app
from tests.test_core import reply
from tests.test_malay_orders_voice import make_service, new_state
from tests.test_server import ENV, KEY, SentRecorder



def finished_without_sizes():
    service = make_service(reply("ok"))
    service.config = {**service.config, "pricing": json.loads(Path("config/business_config.example.json").read_text(encoding="utf-8"))["pricing"]}
    state = new_state()
    state.greeted = state.service_checked = state.contact_confirmed = True
    state.stage = "done"
    state.verified.update({"surfaces": ["walls"], "customer_name": "Siti", "phone": "+60123456789"})     # no sizes at all
    service.store.save(state)
    return service, state


class UnpricedJobTests(unittest.TestCase):
    def test_the_job_is_flagged_for_the_owner_with_the_reason(self):
        service, state = finished_without_sizes()
        reply_text = service._with_quote(state, "Thanks!")
        self.assertEqual((state.quote_status, state.needs_human, state.attention), ("needs_inspection", True, True))
        self.assertIsNone(state.quote)
        self.assertNotEqual(reply_text, "Thanks!")                        # the customer is told the team will look at it
        service.store.save(state)
        summaries = [e["summary"] for e in service.store.audit(state.conversation_id, 5)]
        self.assertTrue(any("Could not be priced automatically" in s for s in summaries))

    def test_it_shows_in_the_inspect_list_and_cannot_be_approved_by_mistake(self):
        service, state = finished_without_sizes()
        service._with_quote(state, "Thanks!")
        service.store.save(state)
        api = TestClient(create_app(service, SentRecorder(), ENV))
        listed = api.get("/api/quotes?status=needs_inspection", headers=KEY).json()["quotes"]
        self.assertEqual([q["user_id"] for q in listed], [state.conversation_id])
        res = api.post(f"/api/quotes/{state.conversation_id}/approve", json={"total": 500}, headers=KEY)
        self.assertEqual(res.status_code, 409)
        self.assertIn("could not be priced", res.json()["detail"])


if __name__ == "__main__":
    unittest.main()
