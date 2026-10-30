"""Malaysia PDPA 2010: nothing is read until the customer agrees, and STOP erases everything."""
import unittest

from fastapi.testclient import TestClient

from src import consent
from src.events import IncomingEvent
from src.server import create_app
from tests.test_core import reply
from tests.test_malay_orders_voice import make_service
from tests.test_server import ENV, KEY, SentRecorder

UID = "60123456789"


def service(*replies):
    svc = make_service(*(replies or (reply("Got it. Which surfaces?"), reply("Got it."))))
    svc.config = {**svc.config, "privacy": {"require_consent": True, "notice_version": "v1"}}   # a copy: other tests share the dict
    return svc


def say(svc, text, mid, **kw):
    return svc.handle(IncomingEvent(mid, UID, text=text, **kw))


class WordsTests(unittest.TestCase):
    def test_agree_and_decline(self):
        for text in ("1", " 1 ", "Yes", "ya", "I agree.", "setuju", "OK!"):
            self.assertTrue(consent.agrees(text), text)
        for text in ("2", "No", "tidak", "decline", "tak setuju"):
            self.assertTrue(consent.declines(text), text)
        for text in ("12", "walls", "1 wall", "maybe"):
            self.assertFalse(consent.agrees(text) or consent.declines(text), text)

    def test_only_a_bare_stop_withdraws(self):
        for text in ("stop", "STOP", "Stop.", "delete my data", "padam data saya"):
            self.assertTrue(consent.withdraws(text), text)
        for text in ("stop, I meant 4m", "don't stop", "please stop the walls at 3m", "start over"):
            self.assertFalse(consent.withdraws(text), text)


class FlowTests(unittest.TestCase):
    def test_the_first_message_gets_the_notice_and_nothing_is_read(self):
        svc = service()
        out = say(svc, "hi I want to paint my room 4x4x3", "a")
        self.assertIn("Under Malaysia's PDPA 2010", out[0])
        self.assertIn("Reply 1 to agree", out[0])
        state = svc.store.load(UID)
        self.assertEqual(state.consent, "pending")
        self.assertEqual(state.verified, {})                       # the sizes were not read
        self.assertEqual(svc.store.messages(UID), [])              # and the message was not saved to the chat log

    def test_agreeing_replays_the_first_message(self):
        svc = service(reply("Got it. Which surfaces?"))
        say(svc, "hi I want to paint my room", "a")
        out = say(svc, "1", "b")
        self.assertIn("Which surfaces", out[0])
        state = svc.store.load(UID)
        self.assertEqual((state.consent, state.pending_first), ("granted", ""))
        self.assertGreater(state.consent_at, 0)
        self.assertTrue(any("Agreed to the PDPA notice" in e["summary"] for e in svc.store.audit(UID, 5)))

    def test_declining_stops_everything(self):
        svc = service()
        say(svc, "paint my walls", "a")
        out = say(svc, "2", "b")
        self.assertIn("won't process", out[0])
        state = svc.store.load(UID)
        self.assertEqual((state.consent, state.pending_first), ("declined", ""))
        again = say(svc, "paint my walls 4x4x3", "c")
        self.assertIn("consent", again[0])
        self.assertEqual(svc.store.load(UID).verified, {})
        say(svc, "1", "d")
        self.assertEqual(svc.store.load(UID).consent, "granted")        # they can change their mind

    def test_a_photo_before_consent_is_not_assessed(self):
        svc = service()
        seen = []
        svc.photo_assessor = lambda media_id: seen.append(media_id)
        out = svc.handle(IncomingEvent("p1", UID, type="image", media_id="55"))
        self.assertIn("PDPA", out[0])
        self.assertEqual(seen, [])
        self.assertEqual(svc.store.messages(UID), [])

    def test_a_silent_customer_is_asked_a_few_times_then_left_alone(self):
        svc = service()
        say(svc, "hi", "a")
        answers = [say(svc, "hello?", f"x{i}") for i in range(5)]
        self.assertTrue(answers[0] and answers[1])
        self.assertEqual(answers[-1], [])

    def test_stop_erases_the_chat_the_bookings_and_the_log(self):
        svc = service(reply("Got it. Which surfaces?"), reply("ok"))
        say(svc, "hi paint my room", "a")
        say(svc, "1", "b")
        say(svc, "walls 4x4x3", "c")
        self.assertTrue(svc.store.messages(UID))
        out = say(svc, "STOP", "d")
        self.assertIn("erased", out[0])
        self.assertEqual(svc.store.messages(UID), [])
        self.assertEqual(svc.store.audit(UID, 10), [])
        self.assertEqual(svc.store.load(UID).history, [])
        self.assertEqual(svc.store.load(UID).consent, "")
        self.assertEqual(svc.store.events(1)[0]["kind"], "data_erased")

    def test_stop_inside_a_sentence_is_not_a_withdrawal(self):
        svc = service(reply("Got it. Which surfaces?"), reply("ok"))
        say(svc, "hi paint my room", "a")
        say(svc, "1", "b")
        say(svc, "stop, I meant 4m", "c")
        self.assertTrue(svc.store.messages(UID))

    def test_malay_notice(self):
        svc = service()
        out = say(svc, "saya nak cat dinding bilik tidur saya, tinggi 3 meter", "a")
        self.assertIn("PDPA Malaysia 2010", out[0])
        self.assertIn("Balas 1 untuk setuju", out[0])

    def test_a_business_can_switch_it_off(self):
        svc = service(reply("Hello! Which surfaces?"))
        svc.config = {**svc.config, "privacy": {"require_consent": False}}
        out = say(svc, "hi paint my room", "a")
        self.assertNotIn("PDPA", out[0])

    def test_calls_are_not_gated(self):
        svc = service(reply("Hello! Which surfaces?"))
        out = svc.handle(IncomingEvent("v1", UID, text="hi", channel="voice"))
        self.assertNotIn("PDPA", out[0] if out else "")


class OwnerErasureTests(unittest.TestCase):
    def setUp(self):
        self.svc = service(reply("Got it. Which surfaces?"))
        say(self.svc, "hi paint my room", "a")
        say(self.svc, "1", "b")
        self.api = TestClient(create_app(self.svc, SentRecorder(), ENV))

    def test_the_owner_can_erase_a_customer_and_the_list_shows_consent(self):
        item = self.api.get("/api/pipeline", headers=KEY).json()["quotes"][0]
        self.assertEqual(item["consent"], "granted")
        self.assertEqual(self.api.delete(f"/api/customers/{UID}/data", headers=KEY).status_code, 204)
        self.assertEqual(self.api.get("/api/pipeline", headers=KEY).json()["quotes"], [])
        self.assertEqual(self.api.delete(f"/api/customers/{UID}/data", headers=KEY).status_code, 404)

    def test_a_reviewer_cannot_erase(self):
        res = self.api.delete(f"/api/customers/{UID}/data", headers={**KEY, "x-orbyte-role": "reviewer"})
        self.assertEqual(res.status_code, 403)
        self.assertTrue(self.svc.store.messages(UID))

    def test_it_needs_a_key(self):
        self.assertEqual(self.api.delete(f"/api/customers/{UID}/data").status_code, 401)


if __name__ == "__main__":
    unittest.main()
