"""WhatsApp calls: the webhook events, the LiveKit hand-off, and the voice worker's line to the assistant."""
import asyncio
import hashlib
import hmac
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from src.events import calls_from_meta_payload
from src.server import create_app
from src.service import IncomingService
from src.store import SqliteStore
from tests.test_core import FakeClient
from voice_worker.backend import Backend, spoken

SECRET = "app-secret"
ENV = {"WHATSAPP_VERIFY_TOKEN": "v", "WHATSAPP_APP_SECRET": SECRET, "INCOMING_API_KEY": "key",
       "MESSAGE_WINDOW_SECONDS": "0"}


BASIC = {"business_name": "Test Painting", "services": ["interior painting"], "policies": [],
         "required_fields": ["address"]}


def calls_payload(*calls):
    return {"entry": [{"changes": [{"field": "calls", "value": {"metadata": {"phone_number_id": "biz-1"},
                                                                  "calls": list(calls)}}]}]}


CONNECT = {"id": "wacid.1", "event": "connect", "from": "60123456789",
           "session": {"sdp_type": "offer", "sdp": "v=0 offer"}}
TERMINATE = {"id": "wacid.1", "event": "terminate"}


def signed_post(client, payload):
    raw = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return client.post("/webhook", content=raw, headers={"x-hub-signature-256": sig})


class CallEventTests(unittest.TestCase):
    def test_connect_and_terminate_are_parsed_with_the_caller(self):
        connect, terminate = calls_from_meta_payload(calls_payload(CONNECT, TERMINATE))
        self.assertEqual((connect["id"], connect["event"], connect["phone_number_id"], connect["sdp_type"],
                          connect["sdp"], connect["caller"]), ("wacid.1", "connect", "biz-1", "offer", "v=0 offer", "60123456789"))
        self.assertEqual((terminate["event"], terminate["caller"]), ("terminate", ""))

    def test_other_events_and_junk_are_ignored(self):
        ringing = {"id": "x", "event": "ringing"}
        self.assertEqual(calls_from_meta_payload(calls_payload(ringing, {"event": "connect"}, "junk")), [])
        for junk in (None, [], {"entry": "x"}, {"entry": [None, {"changes": [1, {"field": "messages"}]}]}):
            self.assertEqual(calls_from_meta_payload(junk), [])


class WebhookCallTests(unittest.TestCase):
    def make(self, enabled="true", handler=None):
        self.dir = tempfile.TemporaryDirectory()
        self.service = IncomingService(SqliteStore(Path(self.dir.name) / "t.db"), BASIC, FakeClient())
        self.handled = []
        env = {**ENV, "WHATSAPP_CALLING_ENABLED": enabled}
        return TestClient(create_app(self.service, None, env,
                                     call_handler=handler or (lambda call, e: self.handled.append(call))))

    def kinds(self):
        return [e["kind"] for e in self.service.store.events(20)]

    def test_calls_are_dispatched_once_and_logged(self):
        client = self.make()
        self.assertEqual(signed_post(client, calls_payload(CONNECT)).status_code, 200)
        self.assertEqual(signed_post(client, calls_payload(CONNECT)).status_code, 200)       # Meta delivers twice
        self.assertEqual([c["id"] for c in self.handled], ["wacid.1"])
        self.assertIn("call_handled", self.kinds())
        self.assertIn("1 call event(s)", self.service.store.events(20)[-1]["detail"] + " ".join(
            e["detail"] for e in self.service.store.events(20)))
        signed_post(client, calls_payload(TERMINATE))
        self.assertEqual([c["event"] for c in self.handled], ["connect", "terminate"])

    def test_disabled_by_default(self):
        client = self.make(enabled="false")
        signed_post(client, calls_payload(CONNECT))
        self.assertEqual(self.handled, [])
        self.assertIn("call_ignored", self.kinds())
        self.assertIn("WHATSAPP_CALLING_ENABLED=false", self.service.store.events(5)[0]["detail"])

    def test_calls_switch_on_by_themselves_once_livekit_is_configured(self):
        livekit = {"LIVEKIT_URL": "wss://x", "LIVEKIT_API_KEY": "k", "LIVEKIT_API_SECRET": "s"}
        client = self.make(enabled="")                      # nothing set: off, and the log says what is missing
        signed_post(client, calls_payload(CONNECT))
        self.assertEqual(self.handled, [])
        self.assertIn("LIVEKIT_URL", self.service.store.events(5)[0]["detail"])
        self.dir.cleanup()
        self.dir = tempfile.TemporaryDirectory()
        self.service = IncomingService(SqliteStore(Path(self.dir.name) / "t.db"), BASIC, FakeClient())
        self.handled = []
        env = {**ENV, **livekit}                            # secrets set, flag never touched
        client = TestClient(create_app(self.service, None, env, call_handler=lambda call, e: self.handled.append(call)))
        signed_post(client, calls_payload(CONNECT))
        self.assertEqual(len(self.handled), 1)
        self.dir.cleanup()
        self.dir = tempfile.TemporaryDirectory()
        self.service = IncomingService(SqliteStore(Path(self.dir.name) / "t.db"), BASIC, FakeClient())
        self.handled = []
        client = TestClient(create_app(self.service, None, {**env, "WHATSAPP_CALLING_ENABLED": "false"},
                                       call_handler=lambda call, e: self.handled.append(call)))
        signed_post(client, calls_payload(CONNECT))
        self.assertEqual(self.handled, [])                  # an explicit false still wins

    def test_a_failed_hand_off_is_logged_and_can_be_retried(self):
        attempts = []

        def flaky(call, env):
            attempts.append(call["id"])
            if len(attempts) == 1:
                raise RuntimeError("LiveKit credentials are not configured: LIVEKIT_URL")

        client = self.make(handler=flaky)
        signed_post(client, calls_payload(CONNECT))
        error = [e for e in self.service.store.events(20) if e["kind"] == "call_error"][0]
        self.assertIn("LIVEKIT_URL", error["detail"])
        signed_post(client, calls_payload(CONNECT))                                             # Meta's retry
        self.assertEqual(attempts, ["wacid.1", "wacid.1"])
        self.assertIn("call_handled", self.kinds())

    def test_calls_and_messages_in_one_webhook(self):
        client = self.make()
        payload = calls_payload(CONNECT)
        payload["entry"][0]["changes"].append({"field": "messages", "value": {"messages": [
            {"id": "wamid.1", "from": "60123456789", "type": "text", "text": {"body": "hello"}}]}})
        self.assertEqual(signed_post(client, payload).status_code, 200)
        self.assertEqual(len(self.handled), 1)

    def test_a_bad_signature_never_reaches_the_call_handler(self):
        client = self.make()
        res = client.post("/webhook", content=json.dumps(calls_payload(CONNECT)).encode(),
                          headers={"x-hub-signature-256": "sha256=bad"})
        self.assertEqual((res.status_code, self.handled), (403, []))


class LiveKitHandOffTests(unittest.TestCase):
    """Runs the real hand-off code against a stand-in for the livekit package."""

    def stub(self):
        calls = {}

        class Request:
            USER_INITIATED = "user_initiated"

            def __init__(self, **kwargs):
                self.kwargs = kwargs

        class Connector:
            async def accept_whatsapp_call(self, request):
                calls["accept"] = request.kwargs

            async def disconnect_whatsapp_call(self, request):
                calls["disconnect"] = request.kwargs

        class LiveKitAPI:
            def __init__(self, **kwargs):
                calls["connect"] = kwargs
                self.connector = Connector()

            async def aclose(self):
                calls["closed"] = True

        api = types.SimpleNamespace(LiveKitAPI=LiveKitAPI, AcceptWhatsAppCallRequest=Request,
                                    DisconnectWhatsAppCallRequest=Request)
        dispatch = types.SimpleNamespace(RoomAgentDispatch=lambda **kw: kw)
        modules = {"livekit": types.SimpleNamespace(api=api), "livekit.api": api,
                   "livekit.protocol": types.SimpleNamespace(agent_dispatch=dispatch),
                   "livekit.protocol.agent_dispatch": dispatch}
        return calls, mock.patch.dict(sys.modules, modules)

    ENV = {"LIVEKIT_URL": "wss://x.livekit.cloud", "LIVEKIT_API_KEY": "k", "LIVEKIT_API_SECRET": "s",
           "WHATSAPP_TOKEN": "tok"}

    def test_connect_accepts_the_call_and_dispatches_the_agent_with_the_caller(self):
        from src.whatsapp_calling import handle_call_event
        calls, patched = self.stub()
        event = {"id": "wacid.1", "event": "connect", "phone_number_id": "biz-1", "sdp": "offer", "sdp_type": "offer",
                 "caller": "60123456789"}
        with patched:
            handle_call_event(event, self.ENV)
        accept = calls["accept"]
        self.assertEqual((accept["whatsapp_phone_number_id"], accept["whatsapp_call_id"], accept["room_name"]),
                         ("biz-1", "wacid.1", "wa-call-wacid.1"))
        self.assertEqual(accept["sdp"], {"type": "offer", "sdp": "offer"})
        self.assertTrue(accept["wait_until_answered"])
        agent = accept["agents"][0]
        self.assertEqual(agent["agent_name"], "orbyte-whatsapp")
        self.assertEqual(json.loads(agent["metadata"]), {"user_id": "60123456789", "call_id": "wacid.1"})
        self.assertTrue(calls["closed"])

    def test_without_a_caller_the_call_stays_separate_and_the_wait_can_be_switched_off(self):
        from src.whatsapp_calling import handle_call_event
        calls, patched = self.stub()
        event = {"id": "wacid.2", "event": "connect", "phone_number_id": "", "sdp": "offer", "sdp_type": "offer"}
        with patched:
            handle_call_event(event, {**self.ENV, "WHATSAPP_PHONE_NUMBER_ID": "biz-9", "WHATSAPP_CALL_WAIT_FOR_AGENT": "false"})
        self.assertEqual(json.loads(calls["accept"]["agents"][0]["metadata"])["user_id"], "call-wacid.2")
        self.assertFalse(calls["accept"]["wait_until_answered"])
        self.assertEqual(calls["accept"]["whatsapp_phone_number_id"], "biz-9")

    def test_terminate_hangs_up_and_bad_events_fail_loudly(self):
        from src.whatsapp_calling import handle_call_event
        calls, patched = self.stub()
        with patched:
            handle_call_event({"id": "wacid.1", "event": "terminate"}, self.ENV)
            self.assertEqual(calls["disconnect"]["whatsapp_call_id"], "wacid.1")
            with self.assertRaises(ValueError):
                handle_call_event({"id": "c", "event": "connect", "sdp": "", "sdp_type": "offer"}, self.ENV)
            with self.assertRaises(RuntimeError):
                handle_call_event({"id": "c", "event": "connect", "sdp": "o", "sdp_type": "offer"}, self.ENV)  # no phone id
        with self.assertRaises(RuntimeError) as err:
            handle_call_event({"id": "c", "event": "terminate"}, {})
        self.assertIn("LIVEKIT_URL", str(err.exception))


class VoiceWorkerBackendTests(unittest.TestCase):
    def test_replies_are_made_speakable(self):
        recap = "Here's what I have:\n- Address: 12 Jalan Bunga\n- Surfaces: walls\n\nIs everything correct?"
        text = spoken(["Thank you, I've noted this.", recap])
        self.assertNotIn("\n", text)
        self.assertNotIn("- ", text)
        self.assertIn("Address: 12 Jalan Bunga. Surfaces: walls", text)
        self.assertEqual(spoken([]), "")
        self.assertEqual(spoken(["**bold** and `code`"]), "bold and code")
        long = spoken(["Sentence number one is here. " * 80])
        self.assertLessEqual(len(long), 700)
        self.assertTrue(long.endswith("."))

    def test_each_utterance_is_a_text_message_from_the_caller(self):
        sent = []

        class Response:
            def __init__(self, data):
                self.data = data

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, *args):
                return json.dumps(self.data).encode()

        def fake_urlopen(request, timeout=0):
            sent.append((request.full_url, request.get_header("X-api-key"), json.loads(request.data)))
            return Response({"replies": ["Which surfaces?", "Walls or ceiling?"], "lang": "ms"})

        backend = Backend("https://app.example/", "secret", "60123456789", "wacid.1")
        with mock.patch("urllib.request.urlopen", fake_urlopen):
            reply = asyncio.run(backend.ask("saya nak cat bilik"))
            asyncio.run(backend.ask("dinding"))
        self.assertEqual(reply, "Which surfaces? Walls or ceiling?")
        url, key, body = sent[0]
        self.assertEqual((url, key), ("https://app.example/incoming", "secret"))
        self.assertEqual((body["user_id"], body["type"], body["text"], body["channel"]),
                         ("60123456789", "text", "saya nak cat bilik", "voice"))
        self.assertNotEqual(body["message_id"], sent[1][2]["message_id"])        # every utterance is its own message
        self.assertEqual(backend.lang, "ms")

    def test_failures_become_clear_errors(self):
        import urllib.error
        backend = Backend("https://app.example", "k", "u", "c")
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            with self.assertRaises(RuntimeError):
                asyncio.run(backend.ask("hello"))

    def test_the_voice_conversation_is_the_customers_conversation(self):
        directory = tempfile.TemporaryDirectory()
        service = IncomingService(SqliteStore(Path(directory.name) / "t.db"), BASIC, FakeClient(
            json.dumps({"reply": "What is the address?", "extracted_fields": {}, "missing_fields": [], "status": "collecting_information"})))
        client = TestClient(create_app(service, None, ENV))
        body = {"message_id": "call-1:1", "user_id": "60123456789", "type": "text", "text": "hello", "channel": "voice"}
        self.assertEqual(client.post("/incoming", json=body, headers={"x-api-key": "key"}).status_code, 200)
        self.assertEqual(service.store.load("60123456789").channel["phone"], "+60123456789")
        directory.cleanup()


if __name__ == "__main__":
    unittest.main()
