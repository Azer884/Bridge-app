import base64
import hashlib
import hmac
import io
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fastapi.testclient import TestClient

from src.assessment import ConditionAssessment
from src.events import IncomingEvent, calls_from_meta_payload, from_flat, from_meta_payload
from src.server import create_app
from src.service import IncomingService
from src.store import SqliteStore
from src.whatsapp import WhatsAppSender, valid_signature

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
    def __init__(self, ok=True):
        self.sent, self.ok, self.last_error = [], ok, "HTTP 401 expired token"

    def send_text(self, to, text):
        self.sent.append((to, text))
        return self.ok


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

    def test_meta_call_connect_and_terminate_are_parsed(self):
        payload = {"entry": [{"changes": [{"field": "calls", "value": {
            "metadata": {"phone_number_id": "business-id"},
            "calls": [{"id": "call-1", "event": "connect", "session": {
                "sdp_type": "offer", "sdp": "offer-sdp"}},
                {"id": "call-1", "event": "terminate"}]}}]}]}
        connect, terminate = calls_from_meta_payload(payload)
        self.assertEqual((connect["id"], connect["event"], connect["phone_number_id"],
                          connect["sdp_type"], connect["sdp"]),
                         ("call-1", "connect", "business-id", "offer", "offer-sdp"))
        self.assertEqual((terminate["id"], terminate["event"]), ("call-1", "terminate"))

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

    def photo_service(self, assessor):
        service = make_service()
        service.photo_assessor = assessor
        return service

    def test_photo_is_assessed_summarised_and_stored(self):
        seen = []
        def assessor(media_id):
            seen.append(media_id)
            return ConditionAssessment("moderate", ("cracks", "water_damage"), (), 0.9, "vision")
        service = self.photo_service(assessor)
        reply = service.handle(IncomingEvent("m1", "u", type="image", media_id="55"))[0]
        self.assertEqual(seen, ["55"])
        self.assertIn("moderate wear or damage", reply)
        self.assertIn("cracks, water damage", reply)
        self.assertIn("address", reply.lower())            # the next question is still asked
        self.assertEqual(service.store.load("u").photo_assessment["level"], "moderate")

    def test_second_photo_keeps_the_worse_level(self):
        results = iter([ConditionAssessment("severe", ("mould",), (), 0.9, "vision"),
                        ConditionAssessment("good", (), (), 0.9, "vision")])
        service = self.photo_service(lambda media_id: next(results))
        service.handle(IncomingEvent("m1", "u", type="image", media_id="1"))
        service.handle(IncomingEvent("m2", "u", type="image", media_id="2"))
        saved = service.store.load("u").photo_assessment
        self.assertEqual((saved["level"], saved["issues"]), ("severe", ["mould"]))

    def test_photo_failure_or_low_confidence_falls_back_to_the_team_reply(self):
        def broken(media_id):
            raise RuntimeError("download failed")
        for assessor in (broken, lambda m: None, lambda m: ConditionAssessment("good", (), (), 0.2, "vision")):
            service = self.photo_service(assessor)
            reply = service.handle(IncomingEvent("m1", "u", type="image", media_id="1"))[0]
            self.assertIn("passed your photo to our team", reply)
            self.assertIsNone(service.store.load("u").photo_assessment)

    def quoting_service(self, photo=None):
        config = json.loads((Path(__file__).resolve().parent.parent / "config"
                             / "business_config.example.json").read_text(encoding="utf-8"))
        calls = []
        def finishing(state, text, config, client):
            calls.append(text)
            if len(calls) == 1:
                state.verified.update({"room_length_m": 4.0, "room_width_m": 3.0, "room_height_m": 2.5,
                                       "surfaces": ["walls", "ceiling"]})
                state.stage = "done"
            return SimpleNamespace(reply="Perfect.", status="ready_for_estimate")
        directory = tempfile.TemporaryDirectory()
        service = IncomingService(SqliteStore(Path(directory.name) / "q.db"), config, None, handler=finishing)
        service._directory = directory
        if photo:
            state = service.store.load("u")
            state.photo_assessment = photo
            service.store.save(state)
        return service

    def test_finished_job_is_priced_for_the_sme_and_the_customer_sees_no_number(self):
        service = self.quoting_service()
        reply = service.handle(IncomingEvent("m1", "u", text="yes"))[0]
        self.assertEqual(reply, "Perfect.")
        state = service.store.load("u")
        self.assertEqual(state.quote_status, "pending_approval")
        self.assertAlmostEqual(sum(state.quote["breakdown"].values()), state.quote["total"], places=2)
        self.assertEqual(service.handle(IncomingEvent("m2", "u", text="thanks")), ["Perfect."])   # priced once
        (draft,) = service.quotes()
        self.assertEqual(draft["user_id"], "u")
        self.assertIn("Labour", draft["quote"]["breakdown"])

    def test_approval_sends_only_the_total_and_marks_it_approved(self):
        service = self.quoting_service()
        service.handle(IncomingEvent("m1", "u", text="yes"))
        total = service.store.load("u").quote["total"]
        sent = []
        self.assertTrue(service.approve_quote("u", lambda text: sent.append(text) or True))
        self.assertIn(f"MYR {total:,.2f}", sent[0])
        for word in ("Labour", "Materials", "breakdown", "profit"):
            self.assertNotIn(word, sent[0])
        self.assertEqual(service.store.load("u").quote_status, "approved")
        with self.assertRaises(ValueError):
            service.approve_quote("u", lambda text: True)               # cannot approve twice

    def test_sme_can_override_the_total_and_a_failed_send_keeps_it_pending(self):
        service = self.quoting_service()
        service.handle(IncomingEvent("m1", "u", text="yes"))
        self.assertFalse(service.approve_quote("u", lambda text: False, total=999.0))
        self.assertEqual(service.store.load("u").quote_status, "pending_approval")
        sent = []
        service.approve_quote("u", lambda text: sent.append(text) or True, total=999.0)
        self.assertIn("MYR 999.00", sent[0])

    def test_severe_photo_gives_no_price_and_flags_a_human(self):
        severe = {"level": "severe", "issues": ["mould"], "complexity_flags": [], "confidence": 0.9, "source": "vision"}
        service = self.quoting_service(photo=severe)
        reply = service.handle(IncomingEvent("m1", "u", text="yes"))[0]
        self.assertIn("inspection", reply)
        state = service.store.load("u")
        self.assertEqual((state.quote_status, state.needs_human), ("needs_inspection", True))
        self.assertEqual(service.quotes(), [])                          # nothing to approve

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


class FetchMediaTests(unittest.TestCase):
    def fetch(self, media_id, responses):
        def fake_urlopen(req, timeout=0):
            return io.BytesIO(responses.pop(0))
        with mock.patch("src.whatsapp.urllib.request.urlopen", fake_urlopen):
            return WhatsAppSender("tok", "123").fetch_media(media_id)

    def test_downloads_through_the_two_graph_steps(self):
        meta = json.dumps({"url": "https://lookaside.example/img", "mime_type": "image/jpeg"}).encode()
        self.assertEqual(self.fetch("42", [meta, b"jpeg bytes"]), (b"jpeg bytes", "image/jpeg"))

    def test_rejects_bad_ids_non_https_urls_and_oversized_images(self):
        with self.assertRaises(ValueError):
            self.fetch("../x", [])
        with self.assertRaises(ValueError):
            self.fetch("42", [json.dumps({"url": "http://insecure/img"}).encode()])
        meta = json.dumps({"url": "https://lookaside.example/img", "mime_type": "image/png"}).encode()
        with self.assertRaises(ValueError):
            self.fetch("42", [meta, b"x" * (5 * 1024 * 1024 + 1)])


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

    def test_existing_signed_webhook_dispatches_calls_and_messages(self):
        handled = []
        env = {**ENV, "WHATSAPP_CALLING_ENABLED": "true"}
        client = TestClient(create_app(make_service(), self.sender, env,
                                       call_handler=lambda call, configured: handled.append(call)))
        payload = meta_body("hello")
        payload["entry"][0]["changes"].append({"field": "calls", "value": {
            "metadata": {"phone_number_id": "business-id"},
            "calls": [{"id": "call-1", "event": "connect", "session": {
                "sdp_type": "offer", "sdp": "offer-sdp"}}]}})
        raw = json.dumps(payload).encode()
        res = client.post("/webhook", content=raw, headers={"x-hub-signature-256": self.sign(raw)})
        self.assertEqual(res.status_code, 200)
        self.assertEqual((len(handled), handled[0]["id"], self.sender.sent),
                         (1, "call-1", [("60123456789", "echo hello")]))

    def test_calls_are_ignored_until_explicitly_enabled(self):
        handled = []
        client = TestClient(create_app(make_service(), self.sender, ENV,
                                       call_handler=lambda call, configured: handled.append(call)))
        payload = {"entry": [{"changes": [{"field": "calls", "value": {
            "calls": [{"id": "call-2", "event": "terminate"}]}}]}]}
        raw = json.dumps(payload).encode()
        res = client.post("/webhook", content=raw, headers={"x-hub-signature-256": self.sign(raw)})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(handled, [])

    def test_events_trail_shows_arrivals_sends_and_failures(self):
        raw = json.dumps(meta_body("hello")).encode()
        self.client.post("/webhook", content=raw, headers={"x-hub-signature-256": self.sign(raw)})
        self.client.post("/webhook", content=raw, headers={"x-hub-signature-256": "sha256=00"})
        kinds = [e["kind"] for e in self.client.get("/api/events", headers={"x-api-key": "key"}).json()["events"]]
        self.assertEqual(kinds, ["webhook_bad_signature", "sent", "webhook"])      # newest first
        self.assertEqual(self.client.get("/api/events").status_code, 401)

    def test_a_failed_send_is_recorded_with_the_reason(self):
        failing = TestClient(create_app(make_service(), SentRecorder(ok=False), ENV))
        raw = json.dumps(meta_body("hello")).encode()
        failing.post("/webhook", content=raw, headers={"x-hub-signature-256": self.sign(raw)})
        events = failing.get("/api/events", headers={"x-api-key": "key"}).json()["events"]
        self.assertEqual(events[0]["kind"], "send_failed")
        self.assertIn("HTTP 401 expired token", events[0]["detail"])

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


class QuoteApiTests(unittest.TestCase):
    def setUp(self):
        self.sender = SentRecorder()
        self.service = ServiceTests().quoting_service()
        self.service.handle(IncomingEvent("m1", "60123456789", text="yes"))
        self.api = TestClient(create_app(self.service, self.sender, ENV))

    def test_requires_the_api_key(self):
        self.assertEqual(self.api.get("/api/quotes").status_code, 401)
        self.assertEqual(self.api.post("/api/quotes/60123456789/approve").status_code, 401)

    def test_sme_lists_the_breakdown_then_approves_and_the_customer_gets_the_total_only(self):
        (draft,) = self.api.get("/api/quotes", headers=KEY).json()["quotes"]
        self.assertIn("Labour", draft["quote"]["breakdown"])
        res = self.api.post("/api/quotes/60123456789/approve", headers=KEY, json={"total": 1200})
        self.assertEqual(res.json(), {"approved": True})
        ((to, text),) = self.sender.sent
        self.assertEqual(to, "60123456789")
        self.assertIn("MYR 1,200.00", text)
        self.assertNotIn("Labour", text)
        self.assertEqual(self.api.get("/api/quotes", headers=KEY).json()["quotes"], [])
        self.assertEqual(self.api.post("/api/quotes/60123456789/approve", headers=KEY).status_code, 409)

    def test_bad_total_and_missing_sender(self):
        self.assertEqual(self.api.post("/api/quotes/60123456789/approve", headers=KEY, json={"total": -5}).status_code, 422)
        bare = TestClient(create_app(self.service, None, ENV))
        self.assertEqual(bare.post("/api/quotes/60123456789/approve", headers=KEY).status_code, 503)


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
