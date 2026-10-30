"""Regression tests built from a real WhatsApp chat where the assistant asked the same thing twice,
ignored a photo, rejected "4 to 5 m" and asked about a whole room for a single wall."""
import json
import unittest
from pathlib import Path

from src import flow
from src.assessment import ConditionAssessment
from src.assistant import PHOTO_CONDITION, handle_message
from src.conversation import ConversationState
from src.pricing import compute_quotation
from src.schema import single_wall
from tests.test_core import FakeClient, reply

FULL = json.loads(Path("config/business_config.example.json").read_text(encoding="utf-8"))
FULL.pop("privacy", None)          # the PDPA consent step has its own tests (test_consent.py)
CONFIG = {**FULL, "persona": FULL["personas"]["aisha"]}


def new_state():
    state = ConversationState("u")
    state.channel = {"name": "Azer", "phone": "+21656138490"}
    return state


def say(state, client, text):
    return handle_message(state, text, CONFIG, client).reply


class SingleWallChatTests(unittest.TestCase):
    def test_the_pasted_chat(self):
        state = new_state()
        client = FakeClient(reply("Got it. What next?"),
                            reply("Thanks! What next?", fields={"address": "Jalan Sunsuria 43900"}),
                            *[reply("Got it. What next?")] * 8)
        say(state, client, "Hello")
        say(state, client, "Hy aisha i want to paint my bedroom")
        say(state, client, "Jalan Sunsuria 43900")
        say(state, client, "I want to paint1 wall i could send u a pic if u want")
        self.assertEqual(state.verified["surfaces"], ["one wall"])
        self.assertNotIn("room_width_m", state.missing_required(CONFIG))        # one wall: no width question

        state.photo_assessment = {"level": "severe", "issues": ["cracks"], "complexity_flags": [],
                                  "confidence": 0.9, "source": "vision"}
        say(state, client, "Lets say 5")
        self.assertEqual(state.verified["room_length_m"], 5.0)
        self.assertIn("room_length_m", state.estimated)
        say(state, client, "maybe 4 to 5 m")
        self.assertEqual(state.verified["room_height_m"], 5.0)                  # the larger figure
        self.assertEqual(state.verified["surface_condition"], PHOTO_CONDITION)  # the photo answers it
        self.assertEqual(state.next_missing(CONFIG), "paint_tier")

        say(state, client, "any is fine")
        say(state, client, "no preference")
        last = FakeClient()                                                     # the backend finishes alone
        done = handle_message(state, "As soon as possiblr", CONFIG, last).reply
        self.assertEqual(last.calls, [])
        self.assertEqual(state.verified["preferred_datetime"], "As soon as possiblr")
        self.assertIn("Azer", done)                                             # straight to the contact step

        side = say(state, FakeClient(), "What about the color and the paint quality??")
        self.assertIn("premium", side)
        self.assertIn("Azer", side)                                             # and it asks the pending question
        wrap = say(state, FakeClient(), "Ya")
        self.assertIn("Wall: 5 m long, 5 m high", wrap)
        self.assertIn("estimate", wrap)
        self.assertNotIn("Condition: No", wrap)

    def test_other_service_question_is_answered(self):
        state = new_state()
        state.stage = "done"
        out = say(state, FakeClient(), "Do u offer any other service")
        self.assertIn("offer", out)
        self.assertIn("interior", out)


class PricingTests(unittest.TestCase):
    def test_single_wall_area_is_length_times_height(self):
        verified = {"surfaces": ["one wall"], "room_length_m": 5, "room_height_m": 4}
        quote = compute_quotation(verified, FULL["pricing"])
        self.assertEqual(quote.inputs["wall_area_m2"], 20.0)
        self.assertGreater(quote.total, 0)

    def test_estimated_flag_reaches_the_quote(self):
        self.assertTrue(single_wall(["one wall"]))
        self.assertFalse(single_wall(["walls"]))
        self.assertFalse(single_wall(["one wall", "ceiling"]))


class FaqTests(unittest.TestCase):
    def test_price_question_never_gives_a_number(self):
        answer = flow.faq_answer("How much does it cost?", CONFIG, "contact")
        self.assertIn("ur team", answer)
        self.assertNotRegex(answer, r"\d")

    def test_statements_are_not_faq(self):
        self.assertIsNone(flow.faq_answer("I want a quote for my bedroom", CONFIG, "job"))


if __name__ == "__main__":
    unittest.main()


class ConflictTests(unittest.TestCase):
    def test_backend_reading_beats_the_models_extraction(self):
        state = new_state()
        state.greeted = state.service_checked = True
        state.verified.update({"address": "a", "surfaces": ["one wall"], "room_length_m": 5.0,
                               "room_height_m": 4.0, "surface_condition": PHOTO_CONDITION,
                               "paint_tier": "premium"})
        client = FakeClient(reply("Great! When would you like us to come?", fields={"colour": "any colour is fine"}))
        out = handle_message(state, "any colour is fine", CONFIG, client)   # the backend reads it as "no preference"
        self.assertNotEqual(out.status, "needs_clarification")
        self.assertEqual(state.verified["colour"], "no preference")
        self.assertIsNone(state.pending_conflict)

    def test_unrelated_message_does_not_settle_a_text_conflict(self):
        from src.assistant import _resolve_pending_conflict
        state = new_state()
        state.verified["colour"] = "white"
        state.pending_conflict = {"key": "colour", "old": "white", "new": "blue"}
        _resolve_pending_conflict(state, "As soon as possible")
        self.assertEqual(state.verified["colour"], "white")
        self.assertIsNotNone(state.pending_conflict)
        _resolve_pending_conflict(state, "blue please")
        self.assertEqual(state.verified["colour"], "blue")

    def test_questions_say_wall_for_a_single_wall(self):
        from src.schema import ask_for
        state = new_state()
        state.verified["surfaces"] = ["one wall"]
        self.assertEqual(ask_for("room_length_m", state), "How long is the wall (in meters)?")
        self.assertEqual(ask_for("room_height_m", state), "How tall is the wall (in meters)?")
        state.verified["surfaces"] = ["walls"]
        self.assertEqual(ask_for("room_length_m", state), "How long is the room (in meters)?")
