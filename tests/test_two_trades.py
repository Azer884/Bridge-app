"""One business, two trades in the same chat: the trade is read from context (words, then the model) or asked."""
import json
import unittest

from src import trades, views
from src.events import IncomingEvent
from tests.test_core import FakeClient, reply
from tests.test_malay_orders_voice import FULL, make_service

UID = "60111222333"
MIXED = {**FULL, "extra_trades": ["aircon"]}


class ModelClient:
    """A model for the meaning reader: chat(messages, sampling) like the real client, and it remembers what it was sent."""
    def __init__(self, *outputs):
        self.outputs, self.calls = list(outputs), []

    def chat(self, messages, sampling=None):
        self.calls.append(messages)
        return self.outputs.pop(0)


def mixed(*replies):
    svc = make_service(*(replies or [reply("ok")] * 30))
    svc.config = MIXED
    svc.trades = trades.load(MIXED)
    return svc


def say(svc, text, n, **kw):
    out = svc.handle(IncomingEvent(f"m{n}", UID, text=text, **kw))
    return out[0] if out else ""


class DetectTests(unittest.TestCase):
    def test_words_settle_most_messages(self):
        self.assertEqual(trades.detect("my aircon is not cold"), "aircon")
        self.assertEqual(trades.detect("servis aircond rumah saya"), "aircon")
        self.assertEqual(trades.detect("I want to paint my bedroom wall"), "painting")
        self.assertEqual(trades.detect("hi"), None)

    def test_wall_mounted_and_cassette_are_aircon_words_not_painting(self):
        self.assertEqual(trades.detect("clean my wall mounted unit"), None)
        self.assertEqual(trades.detect("servicing a ceiling cassette aircon"), "aircon")

    def test_both_in_one_message(self):
        self.assertEqual(trades.detect("paint the wall and service my aircon"), "both")

    def test_load_adds_the_extra_trade_with_its_own_rules(self):
        loaded = trades.load(MIXED)
        self.assertEqual(set(loaded), {"painting", "aircon"})
        self.assertEqual(loaded["aircon"]["trade_type"], "aircon")
        self.assertIn("unit_count", loaded["aircon"]["required_fields"])
        self.assertEqual(loaded["aircon"]["privacy"], MIXED.get("privacy"))


class RoutingTests(unittest.TestCase):
    def test_a_greeting_is_asked_which_service(self):
        svc = mixed()
        out = say(svc, "hi", 1)
        self.assertIn("painting or aircon", out)
        self.assertEqual(svc.store.load(UID).trade, "")

    def test_an_unclear_message_is_asked_again_in_other_words_then_a_clear_one_decides(self):
        svc = mixed()
        say(svc, "hi", 1)
        again = say(svc, "hmm something at my house", 2)
        self.assertIn("Is it painting, or aircon servicing", again)
        say(svc, "aircon", 3)
        self.assertEqual(svc.store.load(UID).trade, "aircon")

    def test_aircon_words_start_an_aircon_job(self):
        svc = mixed()
        out = say(svc, "my aircon is not cold", 1)
        state = svc.store.load(UID)
        self.assertEqual(state.trade, "aircon")
        self.assertIn("not cold", state.verified["aircon_issue"])
        self.assertTrue(out)

    def test_painting_words_start_a_painting_job(self):
        svc = mixed()
        say(svc, "I want to paint my bedroom wall", 1)
        self.assertEqual(svc.store.load(UID).trade, "painting")

    def test_both_trades_in_a_message_goes_to_the_model_which_reads_it(self):
        svc = mixed()
        svc.use_ai_intents = True
        svc.intent_client = ModelClient(json.dumps({"trade": "aircon", "confidence": 0.9}))
        say(svc, "paint the wall and service my aircon", 1)
        self.assertEqual(svc.store.load(UID).trade, "aircon")

    def test_a_model_that_is_not_sure_means_the_customer_is_asked(self):
        svc = mixed()
        svc.use_ai_intents = True
        svc.intent_client = ModelClient(json.dumps({"trade": "aircon", "confidence": 0.3}))
        out = say(svc, "paint the wall and service my aircon", 1)
        self.assertIn("painting or aircon", out)

    def test_a_single_trade_business_never_asks(self):
        svc = make_service(reply("Got it. Which surfaces?"))
        out = say(svc, "hi", 1)
        self.assertNotIn("aircon servicing", out)


class AirconJobTests(unittest.TestCase):
    def run_chat(self):
        svc = mixed(*[reply("ok")] * 6, reply("Thanks.", fields={"address": "12 Jalan Ampang, Kuala Lumpur"}), *[reply("ok")] * 10)
        steps = ["I need my aircon serviced", "chemical wash please", "2 units", "1.5hp", "water dripping from one",
                 "next Tuesday 10am", "12 Jalan Ampang, Kuala Lumpur"]
        outs = [say(svc, text, i) for i, text in enumerate(steps, start=1)]
        return svc, outs

    def test_each_field_is_read_and_the_next_one_asked(self):
        svc, outs = self.run_chat()
        v = svc.store.load(UID).verified
        self.assertEqual((v["service_type"], v["unit_count"], v["horsepower"]), ("chemical wash", "2", "1.5 HP"))
        self.assertIn("dripping", v["aircon_issue"])
        self.assertIn("preferred_datetime", v)
        self.assertIn("How many aircon units", outs[1])
        self.assertIn("horsepower", outs[2].lower())

    def test_the_questions_are_about_aircon_never_walls(self):
        _svc, outs = self.run_chat()
        for text in outs[:6]:
            self.assertNotIn("wall", text.lower())
            self.assertNotIn("paint", text.lower())

    def test_the_price_comes_from_the_aircon_rate_card_and_the_dashboard_form_matches(self):
        svc, _ = self.run_chat()
        state = svc.store.load(UID)
        quote = svc._reprice(state)
        self.assertIsNotNone(quote)
        self.assertEqual(quote.inputs["unit_count"], 2)
        self.assertEqual(quote.inputs["service_type"], "chemical_wash")
        self.assertEqual(quote.inputs["condition_level"], "moderate")          # dripping is a normal job, not an inspection
        self.assertEqual(quote.status, "draft_ready")
        params = views.params_view(state)
        self.assertEqual(params["kind"], "aircon")
        self.assertEqual([f["key"] for f in params["schema"]], ["unit_count", "service_type", "horsepower", "surface_condition"])
        self.assertEqual(params["ai"]["unit_count"], 2)

    def test_the_owner_can_change_the_units_and_the_price_follows(self):
        svc, _ = self.run_chat()
        state = svc.store.load(UID)
        svc._reprice(state)
        svc.store.save(state)
        two = svc.recalculate(UID, {"unit_count": 2})["quote"]["total"]
        four = svc.recalculate(UID, {"unit_count": 4})["quote"]["total"]
        self.assertGreater(four, two)

    def test_a_compressor_fault_goes_to_a_person(self):
        svc = mixed()
        say(svc, "my aircon compressor is dead", 1)
        state = svc.store.load(UID)
        self.assertTrue(state.needs_human)


class ContextTests(unittest.TestCase):
    def test_hello_answered_with_a_question_repeats_it_and_stores_nothing(self):
        svc = mixed()
        say(svc, "I need my aircon serviced", 1)
        before = dict(svc.store.load(UID).verified)
        svc.use_ai_intents = True
        svc.intent_client = ModelClient(json.dumps({"intent": "confused", "confidence": 0.95}))
        out = say(svc, "Hello?", 2, channel="voice")
        self.assertIn("ask again", out)
        self.assertIn("Which aircon service", out)
        self.assertEqual(svc.store.load(UID).verified, before)

    def test_the_model_is_told_what_was_just_asked(self):
        svc = mixed()
        say(svc, "I need my aircon serviced", 1)
        svc.use_ai_intents = True
        spy = ModelClient(json.dumps({"intent": "other", "confidence": 0.9}))
        svc.intent_client = spy
        say(svc, "Hello?", 2, channel="voice")
        sent = spy.calls[0][-1]["content"]
        self.assertIn("the assistant just asked", sent)
        self.assertIn("aircon service", sent)

    def test_a_low_confidence_reading_changes_nothing(self):
        svc = mixed()
        say(svc, "I need my aircon serviced", 1)
        svc.use_ai_intents = True
        svc.intent_client = ModelClient(json.dumps({"intent": "confused", "confidence": 0.4}))
        out = say(svc, "Hello?", 2, channel="voice")
        self.assertNotIn("ask again", out)


class NewJobOtherTradeTests(unittest.TestCase):
    def test_asking_for_the_other_service_after_a_finished_job_starts_a_new_job(self):
        svc = mixed()
        say(svc, "I want to paint my bedroom wall", 1)
        state = svc.store.load(UID)
        state.stage, state.quote_status = "done", "pending_approval"
        svc.store.save(state)
        say(svc, "I also need my aircon serviced", 2)
        state = svc.store.load(UID)
        self.assertEqual(state.trade, "aircon")
        self.assertEqual(len(state.orders), 1)


if __name__ == "__main__":
    unittest.main()


class BareACTests(unittest.TestCase):
    def test_ac_said_on_its_own_is_an_aircon(self):
        for text in ("I'd like to fix my AC.", "my AC is broken", "the A.C. is leaking", "I need an ac technician"):
            self.assertEqual(trades.detect(text), "aircon", text)

    def test_words_that_only_contain_ac_are_not(self):
        for text in ("I need a place to park", "pack the room", "back wall please"):
            self.assertNotEqual(trades.detect(text), "aircon", text)

    def test_fixing_my_ac_starts_an_aircon_job_not_a_painting_one(self):
        svc = mixed()
        out = say(svc, "I'd like to fix my AC.", 1)
        self.assertEqual(svc.store.load(UID).trade, "aircon")
        self.assertNotIn("paint", out.lower())
        self.assertNotIn("surface", out.lower())


class ReturningCustomerTests(unittest.TestCase):
    def test_an_older_painting_chat_does_not_swallow_a_request_to_fix_the_ac(self):
        svc = mixed()
        state = svc.store.load(UID)
        state.verified.update({"surfaces": ["walls"], "room_length_m": 4.0})          # a painting chat from before: no trade saved
        state.history = [{"role": "user", "content": "paint my wall"}, {"role": "assistant", "content": "How wide?"}]
        svc.store.save(state)
        out = say(svc, "I'd like to fix my AC.", 1)
        saved = svc.store.load(UID)
        self.assertEqual(saved.trade, "aircon")
        self.assertNotIn("surfaces", saved.verified)
        self.assertNotIn("paint", out.lower())

    def test_an_older_painting_chat_carries_on_when_the_customer_does_not_ask_for_aircon(self):
        svc = mixed()
        state = svc.store.load(UID)
        state.verified.update({"surfaces": ["walls"], "room_length_m": 4.0})
        state.history = [{"role": "user", "content": "paint my wall"}, {"role": "assistant", "content": "How wide?"}]
        svc.store.save(state)
        say(svc, "3 meters", 1)
        self.assertEqual(svc.store.load(UID).trade, "painting")

    def test_a_finished_painting_job_then_ac_starts_a_new_aircon_job(self):
        svc = mixed()
        state = svc.store.load(UID)
        state.stage, state.quote_status = "done", "pending_approval"
        state.verified.update({"surfaces": ["walls"]})
        svc.store.save(state)
        say(svc, "I'd like to fix my AC.", 1)
        saved = svc.store.load(UID)
        self.assertEqual((saved.trade, len(saved.orders)), ("aircon", 1))


class TradeLockTests(unittest.TestCase):
    """The chat that went wrong live: "what service do you provide?" must not lock the chat to painting."""

    def test_a_question_about_what_is_offered_lists_both_and_asks(self):
        svc = mixed()
        out = say(svc, "Alright. So what service do you provide, please?", 1)
        self.assertIn("We offer", out)
        self.assertIn("painting", out)
        self.assertIn("aircon servicing", out)
        self.assertEqual(svc.store.load(UID).trade, "")

    def test_the_model_is_not_asked_to_guess_from_a_question_about_services(self):
        svc = mixed()
        svc.use_ai_intents = True
        spy = ModelClient(json.dumps({"trade": "painting", "confidence": 0.99}))
        svc.intent_client = spy
        say(svc, "what service do you provide", 1)
        self.assertEqual(spy.calls, [])
        self.assertEqual(svc.store.load(UID).trade, "")

    def test_a_short_vague_message_is_asked_not_guessed(self):
        svc = mixed()
        svc.use_ai_intents = True
        spy = ModelClient(json.dumps({"trade": "painting", "confidence": 0.99}))
        svc.intent_client = spy
        out = say(svc, "need help please", 1)
        self.assertEqual(spy.calls, [])
        self.assertIn("painting or aircon", out)

    def test_then_the_ac_request_starts_the_aircon_job(self):
        svc = mixed()
        say(svc, "So what service do you provide, please?", 1)
        say(svc, "How about what about fixing the AC?", 2)
        self.assertEqual(svc.store.load(UID).trade, "aircon")

    def test_a_painting_chat_just_begun_can_switch_to_aircon(self):
        svc = mixed()
        say(svc, "I want to paint my wall", 1)
        self.assertEqual(svc.store.load(UID).trade, "painting")
        say(svc, "actually how about fixing the AC instead", 2)
        saved = svc.store.load(UID)
        self.assertEqual(saved.trade, "aircon")
        self.assertNotIn("surfaces", saved.verified)

    def test_a_long_painting_job_is_not_switched_by_a_passing_word(self):
        svc = mixed()
        say(svc, "I want to paint my wall", 1)
        state = svc.store.load(UID)
        state.verified.update({"room_length_m": 4.0, "room_height_m": 3.0, "colour": "white", "paint_tier": "standard"})
        svc.store.save(state)
        say(svc, "the AC room is 4 meters", 2)
        self.assertEqual(svc.store.load(UID).trade, "painting")
