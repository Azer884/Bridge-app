import base64
import hashlib
import hmac
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from src.events import IncomingEvent, from_flat, from_meta_payload
from src.server import create_app
from src.service import IncomingService
from src.store import SqliteStore
from src.whatsapp import valid_signature

CONFIG = {"required_fields": ["address"]}
SECRET = "app-secret"
ENV = {"WHATSAPP_VERIFY_TOKEN": "verify-me", "WHATSAPP_APP_SECRET": SECRET, "INCOMING_API_KEY": "key"}


def meta_body(text="hello", msg_id="wamid.1", kind="text", sender="60123456789"):
    message = {"from": sender, "id": msg_id, "timestamp": "1761200000", "type": kind}
    message[kind] = {"body": text} if kind == "text" else {"id": "media-9", "caption": text}
    return {"entry": [{"changes": [{"value": {
        "contacts": [{"wa_id": sender, "profile": {"name": "Sam Lee"}}], "messages": [message]}}]}]}


def echo_handler(state, text, config, client):
    time.sleep(0.01)
    state.add_turn(text, f"echo {text}")
    return SimpleNamespace(reply=f"echo {text}", status="collecting_information")


def make_service(handler=echo_handler):
    directory = tempfile.TemporaryDirectory()
    service = IncomingService(SqliteStore(Path(directory.name) / "test.db"), CONFIG, None, handler=handler)
    service._directory = directory          # removed when the service is garbage collected
    return service


class SentRecorder:
    def __init__(self):
        self.sent = []

    def send_text(self, to, text):
        self.sent.append((to, text))
        return True


class EventTests(unittest.TestCase):
    def test_meta_text_message_is_flattened(self):
        (event,) = from_meta_payload(meta_body("four metres"))
        self.assertEqual((event.user_id, event.text, event.profile_name, event.phone, event.type),
                         ("60123456789", "four metres", "Sam Lee", "+60123456789", "text"))

    def test_meta_image_and_status_updates(self):
        (event,) = from_meta_payload(meta_body("cracked wall", kind="image"))
        self.assertEqual((event.type, event.media_id, event.text), ("image", "media-9", "cracked wall"))
        self.assertEqual(from_meta_payload({"entry": [{"changes": [{"value": {"statuses": [{"id": "x"}]}}]}]}), [])

    def test_garbage_payloads_do_not_crash(self):
        for junk in (None, [], {"entry": "x"}, {"entry": [None, {"changes": [1]}]}):
            self.assertEqual(from_meta_payload(junk), [])

    def test_flat_event_validation(self):
        self.assertEqual(from_flat({"message_id": "m", "user_id": "u", "text": "hi"}).type, "text")
        self.assertEqual(from_flat({"message_id": "m", "user_id": "u", "type": "audio"}).type, "unsupported")
        for bad in ({}, {"message_id": "m"}, {"message_id": 5, "user_id": "u"}, "x"):
            with self.assertRaises(ValueError):
                from_flat(bad)


class ServiceTests(unittest.TestCase):
    def test_duplicate_delivery_is_answered_once(self):
        service = make_service()
        event = IncomingEvent("wamid.1", "u1", text="hi")
        self.assertEqual(service.handle(event), ["echo hi"])
        self.assertEqual(service.handle(event), [])

    def test_channel_name_and_phone_are_saved_once(self):
        service = make_service()
        service.handle(IncomingEvent("m1", "60123456789", text="hi", profile_name="Sam Lee", phone="+60123456789"))
        state = service.store.load("60123456789")
        self.assertEqual(state.channel, {"name": "Sam Lee", "phone": "+60123456789"})

    def test_crash_releases_the_claim_so_the_retry_is_processed(self):
        def boom(*args):
            raise RuntimeError("model down")
        service = make_service(boom)
        with self.assertRaises(RuntimeError):
            service.handle(IncomingEvent("m1", "u", text="hi"))
        service.handler = echo_handler
        self.assertEqual(service.handle(IncomingEvent("m1", "u", text="hi")), ["echo hi"])

    def test_image_and_unsupported_types(self):
        service = make_service()
        reply = service.handle(IncomingEvent("m1", "u", type="image", media_id="x"))[0]
        self.assertIn("photo", reply)
        self.assertIn("text messages", service.handle(IncomingEvent("m2", "u", type="unsupported"))[0])
        self.assertEqual(service.handle(IncomingEvent("m3", "u", text="   ")), [])

    def test_same_customer_messages_never_interleave_and_customers_run_in_parallel(self):
        service = make_service()
        threads = [threading.Thread(target=service.handle, args=(IncomingEvent(f"m{i}", "u1", text=f"t{i}"),))
                   for i in range(8)]
        threads += [threading.Thread(target=service.handle, args=(IncomingEvent(f"o{i}", f"other{i}", text="hi"),))
                    for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(service.store.load("u1").history), 16)   # no lost updates
        self.assertEqual(len(service.store.messages("u1")), 16)
        self.assertTrue(all(len(service.store.load(f"other{i}").history) == 2 for i in range(8)))


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.sender = SentRecorder()
        self.client = TestClient(create_app(make_service(), self.sender, ENV))

    def sign(self, raw):
        return "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()

    def test_verification_handshake(self):
        ok = self.client.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "verify-me",
                                                 "hub.challenge": "1234"})
        self.assertEqual((ok.status_code, ok.text), (200, "1234"))
        bad = self.client.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "nope",
                                                  "hub.challenge": "1"})
        self.assertEqual(bad.status_code, 403)

    def test_signed_webhook_is_answered_and_replied(self):
        raw = json.dumps(meta_body("hello")).encode()
        res = self.client.post("/webhook", content=raw, headers={"x-hub-signature-256": self.sign(raw)})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.sender.sent, [("60123456789", "echo hello")])

    def test_unsigned_or_badly_signed_webhook_is_rejected(self):
        raw = json.dumps(meta_body()).encode()
        self.assertEqual(self.client.post("/webhook", content=raw).status_code, 403)
        self.assertEqual(self.client.post("/webhook", content=raw,
                                          headers={"x-hub-signature-256": "sha256=00"}).status_code, 403)
        self.assertEqual(self.sender.sent, [])

    def test_incoming_requires_key_and_returns_replies(self):
        body = {"message_id": "m1", "user_id": "u1", "text": "hi"}
        self.assertEqual(self.client.post("/incoming", json=body).status_code, 401)
        res = self.client.post("/incoming", json=body, headers={"x-api-key": "key"})
        self.assertEqual(res.json(), {"replies": ["echo hi"]})
        self.assertEqual(self.client.post("/incoming", json={"text": "x"}, headers={"x-api-key": "key"}).status_code, 422)

    def test_unconfigured_secrets_fail_closed(self):
        bare = TestClient(create_app(make_service(), self.sender, {}))
        raw = b"{}"
        self.assertEqual(bare.post("/webhook", content=raw).status_code, 503)
        self.assertEqual(bare.post("/incoming", json={"message_id": "m", "user_id": "u"}).status_code, 503)

    def test_signature_helper(self):
        raw = b"abc"
        good = "sha256=" + hmac.new(b"s", raw, hashlib.sha256).hexdigest()
        self.assertTrue(valid_signature(raw, good, "s"))
        self.assertFalse(valid_signature(raw, good, ""))
        self.assertFalse(valid_signature(raw, None, "s"))


class FakeModel:
    def __init__(self, output='{"condition_level": "minor", "issues": ["cracks"], "complexity_flags": [], "confidence": 0.9}'):
        self.output, self.calls = output, []

    def chat(self, messages, sampling=None):
        self.calls.append((messages, sampling))
        if isinstance(self.output, Exception):
            raise self.output
        return self.output

    def health(self):
        return {"jobs": {"completed": 3}, "workers": {"ready": 1}, "secret": "dropped"}


PNG = base64.b64encode(b"fake png image bytes").decode()
KEY = {"x-api-key": "key"}


class ModelApiTests(unittest.TestCase):
    def client(self, text=None, vision=None):
        self.text, self.vision = text or FakeModel("hello there"), vision or FakeModel()
        return TestClient(create_app(make_service(), SentRecorder(), ENV,
                                     text_client=self.text, vision_client=self.vision))

    def test_text_chat_returns_text_and_caps_sampling(self):
        api = self.client()
        res = api.post("/api/text/chat", headers=KEY, json={"messages": [{"role": "user", "content": "hi"}],
                                                            "max_tokens": 50})
        self.assertEqual(res.json(), {"text": "hello there"})
        self.assertEqual(self.text.calls[0][1], {"temperature": 0.2, "max_tokens": 50})

    def test_text_chat_validates_input(self):
        api = self.client()
        ok = {"role": "user", "content": "hi"}
        cases = [{"messages": []}, {"messages": [ok] * 21}, {"messages": [{"role": "tool", "content": "x"}]},
                 {"messages": [{"role": "user", "content": "x" * 4001}]},
                 {"messages": [ok], "max_tokens": 100000}]
        for body in cases:
            self.assertEqual(api.post("/api/text/chat", headers=KEY, json=body).status_code, 422)

    def test_model_apis_need_the_key(self):
        api = self.client()
        for method, path, body in (("post", "/api/text/chat", {"messages": [{"role": "user", "content": "x"}]}),
                                   ("post", "/api/vision/assess", {"image_base64": PNG, "mime": "image/png"}),
                                   ("get", "/api/models/health", None)):
            res = getattr(api, method)(path, **({"json": body} if body else {}))
            self.assertEqual(res.status_code, 401, path)
        self.assertEqual(self.text.calls, [])

    def test_vision_assess_returns_validated_assessment(self):
        api = self.client()
        res = api.post("/api/vision/assess", headers=KEY, json={"image_base64": PNG, "mime": "image/png"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual((res.json()["level"], res.json()["issues"], res.json()["source"]),
                         ("minor", ["cracks"], "vision"))

    def test_vision_rejects_bad_input_and_unusable_output(self):
        api = self.client()
        bad = api.post("/api/vision/assess", headers=KEY, json={"image_base64": "***", "mime": "image/png"})
        self.assertEqual(bad.status_code, 422)
        gif = api.post("/api/vision/assess", headers=KEY, json={"image_base64": PNG, "mime": "image/gif"})
        self.assertEqual(gif.status_code, 422)
        api = self.client(vision=FakeModel("I see a wall"))
        res = api.post("/api/vision/assess", headers=KEY, json={"image_base64": PNG, "mime": "image/png"})
        self.assertEqual(res.status_code, 502)

    def test_model_failure_is_a_generic_502(self):
        from src.runpod_client import RunPodError
        api = self.client(text=FakeModel(RunPodError("secret internal detail")))
        res = api.post("/api/text/chat", headers=KEY, json={"messages": [{"role": "user", "content": "x"}]})
        self.assertEqual((res.status_code, res.json()["detail"]), (502, "model unavailable"))

    def test_models_health_reports_both_models_without_extra_fields(self):
        report = self.client().get("/api/models/health", headers=KEY).json()
        self.assertEqual(report["text"], {"jobs": {"completed": 3}, "workers": {"ready": 1}})
        self.assertEqual(report["vision"], report["text"])


if __name__ == "__main__":
    unittest.main()
