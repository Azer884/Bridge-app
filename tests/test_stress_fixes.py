"""Problems found by throwing odd, vague and mixed-up messages at the live model: sizes tied to the wrong word,
answers stored in the wrong field, dates read from decimals, side questions ignored, changes of mind not applied."""
import unittest

from src import flow
from src.answers import address_in, explicit_name, fix_typos, is_address, is_condition, plausible
from src.assistant import handle_message
from src.grounding import cued_sizes, sizes_in, sizes_metric, spoken_decimals
from tests.test_core import FakeClient, reply
from tests.test_malay_orders_voice import CONFIG, new_state


def chat(state, *messages):
    out = None
    for text in messages:
        out = handle_message(state, text, CONFIG, FakeClient(reply("x?"), reply("x?"), reply("x?")))
    return out


class SizeReadingTests(unittest.TestCase):
    def test_each_size_belongs_to_its_own_word(self):
        self.assertEqual(cued_sizes("lebar 4 panjang 6 tinggi 3 meter"),
                         {"room_width_m": 4.0, "room_length_m": 6.0, "room_height_m": 3.0})
        self.assertEqual(cued_sizes("5 wide 4 long"), {"room_width_m": 5.0, "room_length_m": 4.0})
        self.assertEqual(cued_sizes("lima kali empat meter, tinggi tiga meter"), {"room_height_m": 3.0})
        self.assertEqual(cued_sizes("12 kaki kali 10 kaki, tinggi 9 kaki"), {"room_height_m": 2.743})
        self.assertEqual(cued_sizes("length x width is 5 by 3"), {})

    def test_spoken_decimals_and_mixed_units(self):
        self.assertEqual(spoken_decimals("room three point five by 4 point 2"), "room 3.5 by 4.2")
        self.assertEqual(sizes_metric("room is 10ft x 3m"), [3.048, 3.0])
        self.assertEqual(sizes_metric("4 x 5 m"), [4.0, 5.0])
        self.assertIsNone(sizes_metric("4 x 5"))

    def test_numbers_set_side_by_side(self):
        self.assertEqual(sizes_in("walls 4 4 3", loose=True), [4.0, 4.0, 3.0])
        self.assertEqual(sizes_in("walls\n4\n4\n3", loose=True), [4.0, 4.0, 3.0])
        self.assertIsNone(sizes_in("walls 4 4 3"))
        self.assertIsNone(sizes_in("call 012 345 6789", loose=True))

    def test_whole_message_flows(self):
        state = new_state()
        chat(state, "walls 4 4 3")
        v = state.verified
        self.assertEqual((v["room_length_m"], v["room_width_m"], v["room_height_m"]), (4.0, 4.0, 3.0))
        state = new_state()
        chat(state, "room is 10ft x 3m, walls")
        self.assertEqual((state.verified["room_length_m"], state.verified["room_width_m"]), (3.048, 3.0))
        state = new_state()
        chat(state, "12'x10' room, 9' high, walls")
        self.assertEqual(state.verified["room_height_m"], 2.743)
        state = new_state()
        chat(state, "room 3 point 5 by 4 point 2, walls")
        self.assertEqual((state.verified["room_length_m"], state.verified["room_width_m"]), (3.5, 4.2))

    def test_zero_sizes_are_ignored_and_feet_are_remembered(self):
        state = new_state()
        chat(state, "paint walls", "room is 0 by 0")
        self.assertNotIn("room_length_m", state.verified)
        state = new_state()
        chat(state, "bilik saya 15 x 12, dinding", "kaki", "10")
        self.assertEqual(state.verified["room_height_m"], 3.048)           # the 10 is feet too


class FieldCheckTests(unittest.TestCase):
    def test_an_answer_must_fit_its_field(self):
        self.assertFalse(plausible("surface_condition", "12 jalan bunga", "12 jalan bunga"))
        self.assertFalse(plausible("surface_condition", "Ali", "Ali"))
        self.assertTrue(plausible("surface_condition", "peeling", "some peeling near the window"))
        self.assertTrue(is_condition("it's fine"))
        self.assertTrue(is_condition("no problems"))
        self.assertTrue(is_condition("no issues at all"))
        self.assertFalse(is_condition("ok its Ali"))
        self.assertFalse(plausible("preferred_datetime", "2.5 high", "2.5 high"))
        self.assertTrue(plausible("preferred_datetime", "friday 3pm", "friday 3pm"))
        self.assertFalse(plausible("address", "yes that's my number", "yes that's my number"))
        self.assertTrue(is_address("12 Jalan Bunga"))
        self.assertFalse(plausible("colour", "ok standard is fine", "ok standard is fine"))
        self.assertFalse(plausible("customer_name", "What's My Order Again", "What's My Order Again"))

    def test_decimals_are_not_dates(self):
        self.assertIsNone(flow.when_in("2.5 high", strict=True))
        self.assertEqual(flow.when_in("14:30"), "14:30")
        self.assertEqual(flow.when_in("Hi good morning, can you come this Saturday morning?"), "Saturday morning")
        self.assertEqual(flow.when_in("any day except monday"), "any day except monday")
        self.assertEqual(flow.when_in("make it saturday"), "saturday")
        self.assertEqual(flow.date_problem("yesterday"), "date_past")
        self.assertEqual(flow.date_problem("after raya"), "date_need_day")

    def test_a_date_does_not_become_the_condition(self):
        state = new_state()
        state.greeted = state.service_checked = True
        state.verified.update({"surfaces": ["walls"], "room_length_m": 4.0, "room_width_m": 4.0, "room_height_m": 3.0,
                               "paint_tier": "standard", "colour": "white"})
        out = handle_message(state, "yesterday", CONFIG, FakeClient(reply("x?")))
        self.assertIn("passed", out.reply)
        self.assertNotIn("preferred_datetime", state.verified)

    def test_unanswered_condition_is_asked_again_then_left_for_the_owner(self):
        state = new_state()
        state.greeted = state.service_checked = True
        state.verified.update({"surfaces": ["walls"], "room_length_m": 4.0, "room_width_m": 4.0, "room_height_m": 3.0,
                               "paint_tier": "standard", "colour": "white", "preferred_datetime": "friday"})
        first = handle_message(state, "bright", CONFIG, FakeClient(reply("x?", fields={"surface_condition": "bright"}))).reply
        self.assertIn("good condition", first)
        self.assertNotIn("surface_condition", state.verified)
        handle_message(state, "hmm something like that", CONFIG, FakeClient(reply("x?")))
        self.assertEqual(state.verified["surface_condition"], "not described")

    def test_volunteered_details(self):
        self.assertEqual(address_in("at 5 Jalan Mawar, Ali, 0123456789"), "5 Jalan Mawar")
        self.assertEqual(address_in("my address is 12 Jalan Bunga, Taman Melati walls 4x4x3"), "12 Jalan Bunga, Taman Melati")
        self.assertEqual(explicit_name("Hi I'm Sarah and my number is 0123456789"), "Sarah")
        self.assertIsNone(explicit_name("I'm looking to paint my room"))
        self.assertEqual(explicit_name("name: Ali phone: 0123456789"), "Ali")
        self.assertEqual(fix_typos("wals only"), "walls only")
        self.assertEqual(fix_typos("calls tall wall"), "calls tall wall")
        state = new_state()
        chat(state, "Siti 0123456789")
        self.assertEqual((state.verified.get("customer_name"), state.verified.get("phone")), ("Siti", "0123456789"))


class ChangeOfMindTests(unittest.TestCase):
    def job(self):
        state = new_state()
        state.greeted = state.service_checked = True
        state.verified.update({"surfaces": ["walls"], "room_length_m": 4.0, "room_width_m": 4.0, "room_height_m": 3.0,
                               "paint_tier": "standard", "colour": "white", "preferred_datetime": "friday morning"})
        return state

    def test_new_answers_replace_old_ones(self):
        state = self.job()
        chat(state, "actually premium")
        self.assertEqual(state.verified["paint_tier"], "premium")
        chat(state, "change colour to blue")
        self.assertEqual(state.verified["colour"], "blue")
        chat(state, "make it monday")
        self.assertEqual(state.verified["preferred_datetime"], "monday")
        chat(state, "sorry I meant 5 x 5")
        self.assertEqual((state.verified["room_length_m"], state.verified["room_width_m"]), (5.0, 5.0))
        chat(state, "wait height is 2.8")
        self.assertEqual(state.verified["room_height_m"], 2.8)
        chat(state, "no 2.6")
        self.assertEqual(state.verified["room_height_m"], 2.6)
        chat(state, "and also the ceiling")
        self.assertEqual(state.verified["surfaces"], ["walls", "ceiling"])

    def test_a_question_does_not_change_the_tier(self):
        state = self.job()
        chat(state, "what is the difference between economy and premium?")
        self.assertEqual(state.verified["paint_tier"], "standard")

    def test_a_street_number_is_not_a_height(self):
        state = self.job()
        state.last_field = "room_height_m"
        chat(state, "No 5 Jalan Mawar")
        self.assertEqual(state.verified["room_height_m"], 3.0)
        self.assertFalse(flow.is_correction("No 5 Jalan Mawar"))
        self.assertTrue(flow.is_correction("no 2.6"))

    def test_cancel_goes_to_the_owner(self):
        state = self.job()
        out = chat(state, "cancel my order")
        self.assertIn("cancel", out.reply)
        self.assertTrue(state.needs_human and state.attention)


class FirstMessageTests(unittest.TestCase):
    def test_a_question_before_any_job_gets_an_answer_and_the_greeting_comes_first(self):
        for text, expect in (("are you a robot", "virtual assistant"), ("do you give discount", "discount"),
                             ("how do i pay", "payment"), ("is there warranty", "warranty"),
                             ("what paint brands do you use", "economy"), ("i want to book a slot", "availability"),
                             ("do i need to move my furniture", "furniture"), ("tell me a joke", "painting quotes")):
            state = new_state()
            out = chat(state, text)
            self.assertTrue(out.reply.startswith("Hi there, I'm Aisha"), text)
            self.assertIn(expect, out.reply, text)
            self.assertEqual(out.reply.count("Hi there"), 1, text)

    def test_small_talk_is_not_met_with_the_same_line(self):
        state = new_state()
        replies = [chat(state, text).reply for text in ("hi", "hi", "thanks", "ok bye", "???")]
        self.assertIn("Aisha", replies[0])
        self.assertIn("I'm here", replies[1])
        self.assertIn("welcome", replies[2])
        self.assertIn("stopping by", replies[3])
        self.assertIn("didn't catch", replies[4])

    def test_sizes_before_the_service_start_the_quote(self):
        state = new_state()
        out = chat(state, "about 4 to 5 meters long")
        self.assertTrue(state.service_checked)
        self.assertEqual(state.verified["room_length_m"], 5.0)
        self.assertIn("Which surfaces", out.reply)

    def test_other_trades_are_declined_but_walls_are_not(self):
        for text in ("I need wallpaper installed", "need a plumber", "paint kitchen cabinets"):
            self.assertEqual(flow.check_service(text), "unsupported", text)
        self.assertEqual(flow.check_service("no wallpaper, walls 4x4x3"), "supported")
        self.assertEqual(flow.check_service("do i need to move my furniture"), "unknown")
        self.assertEqual(flow.check_service("walls and ceiling, the size of a car park lot"), "supported")

    def test_the_services_question_when_switching_language(self):
        state = new_state()
        out = chat(state, "can speak malay?")
        self.assertIn("Aisha", out.reply)
        self.assertIn("Apa yang boleh kami bantu", out.reply)


class WrapUpTests(unittest.TestCase):
    def test_the_recap_is_not_repeated_when_nothing_changed(self):
        state = new_state()
        state.greeted = state.service_checked = state.contact_confirmed = True
        state.stage = "wrapup"
        state.verified.update({"surfaces": ["walls"], "room_length_m": 4.0, "room_width_m": 4.0, "room_height_m": 3.0,
                               "surface_condition": "good", "paint_tier": "standard", "colour": "white",
                               "preferred_datetime": "friday", "address": "12 Jalan Bunga"})
        out = chat(state, "hmm")
        self.assertNotIn("Here's what I have", out.reply)
        self.assertIn("anything you'd like to change", out.reply)
        out = chat(state, "I want to paint another room too")
        self.assertIn("another room", out.reply)

    def test_names_that_are_not_names(self):
        from src import contact
        for text in ("idk", "What's My Order Again", "skip", "later"):
            self.assertIsNone(contact.find_name(text, allow_bare=True), text)
        self.assertEqual(contact.find_name("ok its Ali", allow_bare=True), "Ali")


if __name__ == "__main__":
    unittest.main()
