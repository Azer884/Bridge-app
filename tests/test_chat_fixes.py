"""Problems found in a real call and a real text chat: spoken numbers, sizes tied to words, wall counts, asking for a
person, a request outside the services, abuse, other alphabets, and a voice for each character."""
import json
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from src import flow
from src.assistant import handle_message
from src.grounding import cued_sizes, numbers_in, sizes_in
from src.guard import is_abusive
from src.persona import clean
from src.server import create_app
from tests.test_core import FakeClient, reply
from tests.test_malay_orders_voice import CONFIG, FULL, KEY, make_service, new_state
from voice_worker.backend import Backend, spoken


def fresh():
    state = new_state()
    state.greeted = state.service_checked = True
    return state


class SpokenSizeTests(unittest.TestCase):
    def test_number_words_by_number_words(self):
        self.assertEqual(sizes_in("I told you it's three by four"), [3.0, 4.0])
        self.assertEqual(sizes_in("3x4x5"), [3.0, 4.0, 5.0])
        self.assertIsNone(sizes_in("it's by four or something"))
        state = fresh()
        state.verified.update({"surfaces": ["ceiling"]})
        handle_message(state, "I told you it's three by four", CONFIG, FakeClient(reply("x?")))
        self.assertEqual((state.verified["room_length_m"], state.verified["room_width_m"]), (3.0, 4.0))

    def test_speech_to_text_writes_seventh_for_seven(self):
        self.assertEqual(numbers_in("Seventh"), [7.0])
        self.assertEqual(numbers_in("the second room"), [])               # "second" and "first" are never numbers
        state = fresh()
        state.verified.update({"surfaces": ["ceiling"], "room_length_m": 3.0, "room_width_m": 4.0})
        handle_message(state, "Seventh", CONFIG, FakeClient(reply("x?")))
        self.assertEqual(state.verified["room_height_m"], 7.0)

    def test_sizes_tied_to_a_word_and_a_squares_perimeter(self):
        said = "I have a square room to be painted it's perimeter is 16 metres with a height of 3 meters"
        self.assertEqual(cued_sizes(said), {"room_height_m": 3.0, "room_length_m": 4.0, "room_width_m": 4.0})
        self.assertEqual(cued_sizes("it is 4 m long and 3 m wide"), {"room_length_m": 4.0, "room_width_m": 3.0})
        self.assertEqual(cued_sizes("the perimeter is 16 metres"), {})          # not a square: nothing to say about one side
        state = fresh()
        state.verified.update({"surfaces": ["walls", "ceiling"]})
        out = handle_message(state, said, CONFIG, FakeClient(reply("x?")))
        v = state.verified
        self.assertEqual((v["room_length_m"], v["room_width_m"], v["room_height_m"]), (4.0, 4.0, 3.0))
        self.assertIn("paint quality", out.reply.lower())                      # nothing about the size is asked again

    def test_four_walls_is_not_one_wall(self):
        state = fresh()
        handle_message(state, "I have wall to be painted", CONFIG, FakeClient(reply("x?")))
        self.assertEqual(state.verified["surfaces"], ["one wall"])
        handle_message(state, "It's 4 walls each 4x4", CONFIG, FakeClient(reply("x?")))
        self.assertEqual(state.verified["surfaces"], ["walls"])
        self.assertNotIn("one wall", json.dumps(state.verified))


class ConversationHandlingTests(unittest.TestCase):
    def test_what_do_you_think_is_not_the_services_question(self):
        self.assertIsNone(flow.faq_answer("Hello? What do you think", CONFIG, "job"))
        self.assertIn("offer", flow.faq_answer("What do you offer?", CONFIG, "job"))
        self.assertIn("offer", flow.faq_answer("what can you paint?", CONFIG, "job"))

    def test_asking_for_a_person_is_a_handoff_not_the_same_question_again(self):
        state = new_state()
        out = handle_message(state, "Can I speak with a live agent", CONFIG, FakeClient())
        self.assertTrue(state.needs_human and state.attention)
        self.assertIn("Daniel Tan", out.reply)
        self.assertNotIn("What can we help you with today", out.reply)
        self.assertEqual(state.followups[0]["text"], "Can I speak with a live agent")
        for text in ("talk to the owner please", "I want a real person", "call me", "cakap dengan pemilik"):
            self.assertTrue(flow.wants_human(text), text)
        self.assertFalse(flow.wants_human("I want to paint my human-sized door"))

    def test_a_request_outside_the_services_is_declined_once_then_not_repeated(self):
        state = new_state()
        first = handle_message(state, "I need the exterior of my condo painted", CONFIG, FakeClient()).reply
        self.assertIn("interior", first)
        again = handle_message(state, "hello?", CONFIG, FakeClient()).reply
        self.assertIn("passed your request to Daniel Tan", again)
        self.assertNotEqual(first, again)
        self.assertNotIn("What can we help you with today", again)
        handle_message(state, "test", CONFIG, FakeClient())
        out = handle_message(state, "ok I want my bedroom walls painted", CONFIG, FakeClient(reply("Which surfaces?")))
        self.assertTrue(state.service_checked and not state.declined)           # an interior job starts a normal quote

    def test_the_services_question_is_not_asked_three_times(self):
        state = new_state()
        first = handle_message(state, "hello", CONFIG, FakeClient()).reply
        second = handle_message(state, "test", CONFIG, FakeClient()).reply
        third = handle_message(state, "hello?", CONFIG, FakeClient()).reply
        self.assertIn("Aisha", first)
        self.assertIn("Which room", second)
        self.assertNotIn("Aisha", third)                                     # a short help line, not the greeting again
        self.assertIn("Which room", third)

    def test_abuse_gets_a_polite_line_and_then_a_person(self):
        state = fresh()
        client = FakeClient()
        for text in ("Nigga I have wall to be painted", "you stupid bitch", "fuck you"):
            out = handle_message(state, text, CONFIG, client)
        self.assertEqual(client.calls, [])                                   # never sent to the model
        self.assertEqual(state.history, [])                                  # and never kept in the chat
        self.assertTrue(state.needs_human)
        self.assertIn("A member of our team", out.reply)
        state = fresh()
        warned = handle_message(state, "stupid nigger", CONFIG, FakeClient()).reply
        self.assertIn("respectful", warned)
        self.assertTrue(is_abusive("babi") and is_abusive("Fuck off"))
        self.assertFalse(is_abusive("the wall is a bit shitty") or is_abusive("class action"))

    def test_another_alphabet_is_asked_to_use_english_or_malay(self):
        self.assertTrue(flow.is_foreign_script("وخوية السلام. نادي حيت. حب لدينا"))
        self.assertFalse(flow.is_foreign_script("Selamat pagi, saya nak cat bilik"))
        self.assertFalse(flow.is_foreign_script("ok"))
        client = FakeClient()
        out = handle_message(new_state(), "وخوية السلام. نادي حيت. حب لدينا", CONFIG, client)
        self.assertIn("English or Bahasa Malaysia", out.reply)
        self.assertEqual(client.calls, [])


class VoicePerCharacterTests(unittest.TestCase):
    def test_every_character_has_its_own_voice(self):
        voices = {name: p["voice"] for name, p in FULL["personas"].items()}
        self.assertEqual(len(set(voices.values())), 3)

    def test_a_voice_can_be_saved_and_must_be_an_id(self):
        base = {k: v for k, v in FULL["personas"]["aisha"].items() if not k.endswith("_ms")}
        self.assertEqual(clean({**base, "voice": "abc-123_x.y"})["voice"], "abc-123_x.y")
        self.assertNotIn("voice", clean({k: v for k, v in base.items() if k != "voice"}))
        for bad in ("two words", "x" * 81, 42, "a;b"):
            with self.assertRaises(ValueError):
                clean({**base, "voice": bad})

    def test_the_worker_reads_the_active_character(self):
        class Response:
            def __init__(self, data):
                self.data = data

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, *args):
                return json.dumps(self.data).encode()

        seen = []

        def fake_urlopen(request, timeout=0):
            seen.append((request.full_url, request.get_header("X-api-key")))
            return Response({"personas": {"ben": {"name": "Ben", "voice": "voice-b"}}, "active": "ben"})

        import asyncio
        backend = Backend("https://app.example/", "secret", "601", "call-1")
        with mock.patch("urllib.request.urlopen", fake_urlopen):
            persona = asyncio.run(backend.persona())
        self.assertEqual(persona, {"name": "Ben", "voice": "voice-b"})
        self.assertEqual(seen, [("https://app.example/api/personas", "secret")])
        with mock.patch("urllib.request.urlopen", side_effect=OSError("down")):
            self.assertEqual(asyncio.run(Backend("https://app.example", "k", "u", "c").persona()), {})

    def test_the_voice_says_meters(self):
        self.assertEqual(spoken(["How long is the room (in metres)?"]), "How long is the room (in meters)?")
        self.assertEqual(spoken(["Metres or 1 metre?"]), "Meters or 1 meter?")


class WidthByLengthTests(unittest.TestCase):
    def ceiling(self):
        state = fresh()
        state.verified.update({"surfaces": ["ceiling"]})
        return state

    def test_the_customers_own_order_is_followed(self):
        state = self.ceiling()
        handle_message(state, "it's 3x4, width x length", CONFIG, FakeClient(reply("x?")))
        self.assertEqual((state.verified["room_width_m"], state.verified["room_length_m"]), (3.0, 4.0))
        state = self.ceiling()
        handle_message(state, "length x width is 5 by 3", CONFIG, FakeClient(reply("x?")))
        self.assertEqual((state.verified["room_length_m"], state.verified["room_width_m"]), (5.0, 3.0))
        state = self.ceiling()
        handle_message(state, "lebar x panjang 3x4", CONFIG, FakeClient(reply("x?")))
        self.assertEqual((state.verified["room_width_m"], state.verified["room_length_m"]), (3.0, 4.0))
        state = self.ceiling()
        handle_message(state, "3x4", CONFIG, FakeClient(reply("x?")))            # no words: length first
        self.assertEqual((state.verified["room_length_m"], state.verified["room_width_m"]), (3.0, 4.0))

    def test_units_next_to_the_numbers_are_fine(self):
        for text in ("3m x 4m", "3 meters by 4 meters", "3m by 4m"):
            state = self.ceiling()
            handle_message(state, text, CONFIG, FakeClient(reply("x?")))
            self.assertEqual((state.verified["room_length_m"], state.verified["room_width_m"]), (3.0, 4.0), text)
        state = self.ceiling()
        handle_message(state, "10ft x 12ft", CONFIG, FakeClient(reply("x?")))
        self.assertAlmostEqual(state.verified["room_length_m"], 3.048)
        self.assertAlmostEqual(state.verified["room_width_m"], 3.658, places=2)

    def test_a_size_and_a_named_size_in_one_message(self):
        state = self.ceiling()
        handle_message(state, "it is 3x4 and the height is 2.5 meters", CONFIG, FakeClient(reply("x?")))
        v = state.verified
        self.assertEqual((v["room_length_m"], v["room_width_m"], v["room_height_m"]), (3.0, 4.0, 2.5))

    def test_big_numbers_without_a_unit_are_asked_once_not_asked_again(self):
        state = self.ceiling()
        client = FakeClient()
        out = handle_message(state, "it's 12 by 10", CONFIG, client)
        self.assertEqual(out.reply, "Are those 12 by 10 in meters or in feet?")
        self.assertEqual(client.calls, [])
        out = handle_message(state, "feet", CONFIG, FakeClient(reply("x?")))
        self.assertAlmostEqual(state.verified["room_length_m"], 3.658, places=2)
        self.assertAlmostEqual(state.verified["room_width_m"], 3.048, places=2)
        self.assertIsNone(state.pending_sizes)
        self.assertIn("tall", out.reply)                                      # only the height is left to ask
        state = self.ceiling()
        handle_message(state, "12 by 10", CONFIG, FakeClient())
        handle_message(state, "what?", CONFIG, FakeClient(reply("Is that meters or feet?")))
        self.assertIsNone(state.pending_sizes)                                 # an unrelated answer drops it: no loop

    def test_meters_not_metres_in_every_english_reply_including_the_models(self):
        from src.i18n import us_spelling
        self.assertEqual(us_spelling("About 3 metres, or one metre. Metres matter; centimetres too."),
                         "About 3 meters, or one meter. Meters matter; centimeters too.")
        self.assertEqual(us_spelling("Immetrex stays"), "Immetrex stays")
        state = fresh()
        out = handle_message(state, "bedroom walls please", CONFIG,
                             FakeClient(reply("Lovely. How many metres long is it?", fields={"surfaces": ["walls"]})))
        self.assertNotIn("metre", out.reply.lower().replace("meter", ""))
        self.assertTrue(all("metre" not in turn["content"] for turn in state.history if turn["role"] == "assistant"))
        malay = fresh()
        malay.lang = "ms"
        self.assertIn("meter", handle_message(malay, "dinding sahaja", CONFIG, FakeClient(reply("x?"))).reply)


if __name__ == "__main__":
    unittest.main()
