"""Colours people say, a rejection heard on the call, and the aircon job in the customer's message and the estimate letter."""
import hashlib
import hmac
import json
import unittest

from fastapi.testclient import TestClient

from src.answers import is_colour, plausible
from src.pdf import estimate_pdf
from src.quote_message import approved_quote_message, job_lines
from src.server import create_app
from tests.test_core import reply
from tests.test_malay_orders_voice import make_service, new_state
from tests.test_orbyte import UID, hub
from tests.test_server import ENV, KEY, SentRecorder


class ColourTests(unittest.TestCase):
    def test_the_names_people_say_are_colours(self):
        for text in ("maroon", "turquoise", "lavender", "off white", "sky blue", "charcoal", "mint green", "terracotta",
                     "warna jingga", "biru muda", "light grey", "dark brown", "peach"):
            self.assertTrue(is_colour(text), text)

    def test_any_short_plain_answer_to_the_colour_question_is_kept(self):
        for text in ("duck egg", "something like seafoam", "a sandy yellow"):
            self.assertTrue(plausible("colour", text, text), text)

    def test_a_yes_a_day_or_a_question_is_not_a_colour(self):
        for text in ("yes", "tomorrow", "what colours do you have?", "4 meters", "ok"):
            self.assertFalse(plausible("colour", text, text), text)

    def test_a_colour_said_in_the_chat_is_stored(self):
        from src.events import IncomingEvent
        svc = make_service(*[reply("ok")] * 6)
        state = new_state()
        state.greeted = state.service_checked = True
        state.verified.update({"surfaces": ["walls"], "room_length_m": 4.0, "room_width_m": 3.0, "room_height_m": 2.5,
                               "surface_condition": "good", "paint_tier": "standard"})
        svc.store.save(state)
        svc.handle(IncomingEvent("c1", "u", text="maroon please", channel="voice"))
        self.assertIn("maroon", svc.store.load("u").verified.get("colour", ""))


class RejectionOnTheCallTests(unittest.TestCase):
    def setUp(self):
        from tests.test_orbyte import HubLinkTests
        self.case = HubLinkTests("test_reject_blocks_the_send_and_is_recorded")
        self.case.setUp()
        self.api, self.sender, self.service = self.case.api, self.case.sender, self.case.service

    def test_on_a_call_the_reason_is_spoken_and_written(self):
        self.api.get("/api/voice/pending", params={"user_id": UID}, headers=KEY)          # the agent polls: the call is live
        self.api.post(f"/api/quotes/{UID}/reject", json={"reason": "check the height with you"}, headers=hub("approver", "Aisha"))
        spoken = self.api.get("/api/voice/pending", params={"user_id": UID}, headers=KEY).json()["say"]
        self.assertEqual(len(spoken), 1)
        self.assertIn("check the height with you", spoken[0])
        self.assertEqual(len(self.sender.sent), 1)                                        # and the chat has it too
        self.assertIn("check the height with you", str(self.sender.sent[0]))

    def test_without_a_call_it_is_only_written(self):
        self.api.post(f"/api/quotes/{UID}/reject", json={"reason": "check the height with you"}, headers=hub("approver", "Aisha"))
        self.assertEqual(self.api.get("/api/voice/pending", params={"user_id": UID}, headers=KEY).json()["say"], [])
        self.assertEqual(len(self.sender.sent), 1)


class AirconCustomerTextTests(unittest.TestCase):
    JOB = {"service_type": "chemical wash", "unit_count": "2", "horsepower": "1.5 HP", "aircon_issue": "water dripping",
           "address": "12 Jalan Ampang", "preferred_datetime": "Tuesday 10 am"}

    def test_the_estimate_message_lists_the_aircon_job_not_walls(self):
        text = "\n".join(job_lines(self.JOB))
        for part in ("chemical wash", "2", "1.5 HP", "water dripping"):
            self.assertIn(part, text)
        self.assertNotIn("Room", text)
        self.assertNotIn("Surfaces", text)

    def test_a_photo_placeholder_is_not_shown_as_the_problem(self):
        job = {**self.JOB, "aircon_issue": "see the customer's photo"}
        self.assertNotIn("photo", "\n".join(job_lines(job)))

    def test_the_whole_message_goes_out(self):
        msg = approved_quote_message(150.0, "MYR", "CoolBreeze", "en", {"hours_on_site": 2, "crew_size": 2}, self.JOB)
        self.assertIn("chemical wash", msg)
        self.assertIn("150", msg)

    def test_the_letter_says_aircon(self):
        pdf = estimate_pdf("CoolBreeze", "Siti", {**self.JOB, "trade": "aircon"}, {"total": 150.0, "currency": "MYR"})
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertIn(b"Aircon servicing estimate", pdf)


class AirconSpokenAnswersTests(unittest.TestCase):
    def fields(self, *texts):
        from src import trades
        from src.events import IncomingEvent
        from tests.test_two_trades import MIXED, UID as TRADE_UID
        svc = make_service(*[reply("ok")] * 20)
        svc.config, svc.trades = MIXED, trades.load(MIXED)
        for i, text in enumerate(texts):
            svc.handle(IncomingEvent(f"a{i}", TRADE_UID, text=text, channel="voice"))
        return svc.store.load(TRADE_UID).verified

    def test_horsepower_said_in_words(self):
        self.assertEqual(self.fields("my aircon needs servicing", "two horsepower")["horsepower"], "2 HP")
        self.assertEqual(self.fields("my aircon needs servicing", "one and a half horsepower")["horsepower"], "1.5 HP")

    def test_a_plain_service_answers_the_service_question(self):
        v = self.fields("my aircon is not cold", "just a normal service please")
        self.assertEqual(v["service_type"], "general service")

    def test_wash_means_chemical_wash(self):
        self.assertEqual(self.fields("I want to wash my aircon")["service_type"], "chemical wash")


if __name__ == "__main__":
    unittest.main()


class TimeKeepsItsAmPmTests(unittest.TestCase):
    def test_a_time_with_minutes_keeps_am_or_pm(self):
        from src import flow, scheduling
        from src.grounding import normalise_speech
        said = flow.when_in(normalise_speech("Tuesday at half past two"), strict=True)
        self.assertIn("pm", said)
        self.assertEqual(scheduling.parse_preference(said)["hour"], 14)
        self.assertEqual(scheduling.parse_preference(flow.when_in("Tuesday 2:30 pm", strict=True))["hour"], 14)
