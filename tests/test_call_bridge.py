"""Calls: a calm spoken voice, no "dot", chat answers going to the phone while the caller is on it, and the recording
notice in the greeting."""
import hashlib
import importlib.util
import hmac
import json
import unittest

from fastapi.testclient import TestClient

from src.server import create_app
from tests.test_server import CONFIG, ENV, SECRET, SentRecorder, make_service, meta_body
from voice_worker.backend import spoken

KEY = {"x-api-key": ENV["INCOMING_API_KEY"]}


class SpokenWordingTests(unittest.TestCase):
    def test_calm_and_without_symbols(self):
        text = spoken(["Perfect! How tall is the room (in meters)?"])
        self.assertEqual(text, "How tall is the room (in meters)?")
        self.assertNotIn("!", spoken(["Hello! Thanks for calling!"]))
        self.assertEqual(spoken(["Great. What colour would you like?"]), "What colour would you like?")

    def test_numbers_and_dots_are_said_properly(self):
        self.assertEqual(spoken(["The room is 3.5 meters by 4.0 meters."]), "The room is 3 point 5 meters by 4 meters.")
        self.assertEqual(spoken(["Room: 4 m long, 3 m wide"]), "Room: 4 meters long, 3 meters wide")
        self.assertEqual(spoken(["Example Painting Sdn. Bhd. (demo) here..."]), "Example Painting Sdn Bhd here,")
        self.assertEqual(spoken(["cream / beige / grey"]), "cream, beige, grey")
        self.assertNotIn("dot", spoken(["See www.example.com e.g. today"]).lower())

    @unittest.skipUnless(importlib.util.find_spec("livekit"), "LiveKit is not installed in this environment")
    def test_greeting_says_the_call_is_recorded(self):
        import voice_worker.agent as agent_module
        self.assertIn("recorded", agent_module.GREETING)
        self.assertIn("recorded", agent_module.RECORDING_NOTICE)


class ChatDuringCallTests(unittest.TestCase):
    def setUp(self):
        self.sender = SentRecorder()
        self.client = TestClient(create_app(make_service(), self.sender, ENV))

    def sign(self, raw):
        return "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()

    def chat(self, text, msg_id):
        raw = json.dumps(meta_body(text, msg_id=msg_id)).encode()
        self.client.post("/webhook", content=raw, headers={"x-hub-signature-256": self.sign(raw)})

    def pending(self, **extra):
        return self.client.get("/api/voice/pending", params={"user_id": "60123456789", **extra}, headers=KEY).json()

    def test_without_a_call_the_answer_goes_to_whatsapp(self):
        self.chat("hello", "wamid.a")
        self.assertEqual(len(self.sender.sent), 1)
        self.assertEqual(self.pending()["say"], [])

    def test_with_a_call_the_answer_is_spoken_instead(self):
        self.pending()                                   # the voice agent starts polling: the call is live
        self.chat("hello", "wamid.b")
        self.assertEqual(self.sender.sent, [])
        say = self.pending()["say"]
        self.assertEqual(len(say), 1)
        self.assertIn("echo hello", say[0])
        self.assertEqual(self.pending()["say"], [])      # each answer is handed over once

    def test_when_the_call_ends_answers_return_to_whatsapp(self):
        self.pending()
        self.pending(end="true")
        self.chat("hello", "wamid.c")
        self.assertEqual(len(self.sender.sent), 1)

    def test_a_voice_message_marks_the_call_live_and_the_voice_greets_itself(self):
        body = {"message_id": "v1", "user_id": "60123456789", "type": "text", "text": "hello", "channel": "voice"}
        self.client.post("/incoming", json=body, headers=KEY)
        self.chat("anything", "wamid.d")
        self.assertEqual(self.sender.sent, [])

    def test_the_pending_route_needs_the_key(self):
        self.assertEqual(self.client.get("/api/voice/pending", params={"user_id": "x"}).status_code, 401)


if __name__ == "__main__":
    unittest.main()


class HangUpTests(unittest.TestCase):
    def test_goodbye_ends_the_call(self):
        client = TestClient(create_app(make_service(), SentRecorder(), ENV))
        body = {"message_id": "v9", "user_id": "60123456789", "type": "text", "text": "ok thanks, bye", "channel": "voice"}
        self.assertTrue(client.post("/incoming", json=body, headers=KEY).json()["end_call"])
        body.update(message_id="v10", text="I want to paint my bedroom")
        self.assertFalse(client.post("/incoming", json=body, headers=KEY).json()["end_call"])
        body.update(message_id="w1", text="bye", channel="whatsapp")
        self.assertFalse(client.post("/incoming", json=body, headers=KEY).json()["end_call"])   # chat: no call to end
