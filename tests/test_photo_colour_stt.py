"""Colour suggested from a photo, speech-to-text vocabulary, and replies that invent sizes."""
import unittest

from src import flow
from src.events import IncomingEvent
from src.transcribe import normalize_spoken
from src.validation import invented_figures, validate_response
from src.vision import COLOUR_PALETTE, colour_from_output, suggest_colours
from tests.test_core import FakeClient, reply
from tests.test_malay_orders_voice import CONFIG, make_service, new_state
from voice_worker.backend import keyterms


class FakeVision:
    def __init__(self, *texts):
        self.texts = list(texts)

    def chat(self, messages, sampling=None):
        return self.texts.pop(0)


class ColourIntentTests(unittest.TestCase):
    def test_asks_for_a_suggestion(self):
        for text in ("Suggest a colour based on the picture", "can you recommend a color for my room",
                     "what colour will suit it", "cadangkan warna untuk bilik saya"):
            self.assertTrue(flow.wants_colour_suggestion(text), text)
        for text in ("I want blue", "the walls are white now", "3 by 4 meters"):
            self.assertFalse(flow.wants_colour_suggestion(text), text)


class ColourFromPhotoTests(unittest.TestCase):
    def test_output_limited_to_the_palette(self):
        out = colour_from_output({"current": "White", "suggestions": ["white", "sage", "beige", "beige", "teal", "blue"]})
        self.assertEqual(out, {"current": "white", "suggestions": ["beige", "teal", "blue"]})
        self.assertIsNone(colour_from_output({"current": "", "suggestions": ["lime"]}))
        self.assertTrue(set(out["suggestions"]) <= set(COLOUR_PALETTE))

    def test_bad_model_output_is_retried(self):
        client = FakeVision("not json", '{"current": "cream", "suggestions": ["grey", "blue", "green"]}')
        self.assertEqual(suggest_colours(client, b"x" * 10, "image/jpeg")["suggestions"], ["grey", "blue", "green"])

    def service(self):
        service = make_service(reply("Which wall?"))
        service.colour_assessor = lambda media_id: {"current": "cream", "suggestions": ["grey", "blue", "green"]}
        state = new_state()
        state.greeted = state.service_checked = True
        service.store.save(state)
        return service

    def test_photo_first_then_request(self):
        service = self.service()
        service.handle(IncomingEvent("p1", "u", type="image", media_id="55"))
        out = service.handle(IncomingEvent("m1", "u", text="Suggest a colour based on the picture"))
        self.assertIn("cream", out[0])
        self.assertIn("grey, blue or green", out[0])

    def test_request_first_asks_for_the_photo_then_uses_it(self):
        service = self.service()
        out = service.handle(IncomingEvent("m1", "u", text="Suggest a colour for me"))
        self.assertIn("Send me a photo", out[0])
        self.assertTrue(service.store.load("u").awaiting_colour_photo)
        out = service.handle(IncomingEvent("p1", "u", type="image", media_id="55"))
        self.assertIn("grey, blue or green", out[0])
        self.assertFalse(service.store.load("u").awaiting_colour_photo)

    def test_failure_falls_back_to_asking(self):
        service = self.service()

        def boom(media_id):
            raise RuntimeError("endpoint down")

        service.colour_assessor = boom
        service.handle(IncomingEvent("p1", "u", type="image", media_id="55"))
        out = service.handle(IncomingEvent("m1", "u", text="suggest a colour from the photo"))
        self.assertIn("What colour would you like?", out[0])


class SpeechVocabularyTests(unittest.TestCase):
    def test_room_words_are_hinted(self):
        terms = keyterms()
        self.assertIn("sitting room", terms)
        self.assertIn("ruang tamu", terms)

    def test_common_mishears_are_repaired(self):
        self.assertEqual(normalize_spoken("paint the sitting maybe one word please"), "paint the sitting room please")
        self.assertEqual(normalize_spoken("my bed rum"), "my bedroom")


class InventedFigureTests(unittest.TestCase):
    def test_sizes_the_customer_never_gave_are_flagged(self):
        state = new_state()
        state.verified["room_length_m"] = 4.0
        text = "From the perimeter being 16 meters, each wall is 4 meters. How wide is the room?"
        self.assertEqual(invented_figures(text, state, "square room"), ["16 meters"])
        self.assertEqual(invented_figures("Got it, 4 meters long. How wide?", state, "it is 4 m long"), [])
        self.assertEqual(invented_figures("Is the room 12 feet wide?", state, "about 12 feet"), [])

    def test_validation_asks_for_a_rewrite(self):
        state = new_state()
        raw = ('{"reply": "From the perimeter being 16 meters, how tall is it?", "extracted_fields": {}, '
               '"missing_fields": [], "status": "collecting_information"}')
        result = validate_response(raw, state, "it is a square room", CONFIG)
        self.assertTrue(any("never said" in p for p in result.soft_problems))


if __name__ == "__main__":
    unittest.main()
