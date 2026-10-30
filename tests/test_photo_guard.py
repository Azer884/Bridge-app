"""A photo that does not show a wall or ceiling is never used as one."""
import json
import unittest

from src.assessment import ConditionAssessment, from_dict, from_vision_output
from src.events import IncomingEvent
from src.vision import assess_image
from tests.test_core import reply
from tests.test_malay_orders_voice import make_service, new_state
from tests.test_vision import FakeClient


def out(**kw):
    base = {"what_is_it": "a wall", "is_surface": True, "condition_level": "minor", "issues": ["cracks"],
            "complexity_flags": [], "confidence": 0.9}
    base.update(kw)
    return json.dumps(base)


class VisionParsingTests(unittest.TestCase):
    def test_a_wall_is_accepted(self):
        a, _ = assess_image(FakeClient(out()), b"img", "image/jpeg")
        self.assertTrue(a.surface)
        self.assertEqual((a.level, a.issues, a.confidence), ("minor", ("cracks",), 0.9))

    def test_the_model_says_it_is_not_a_surface(self):
        for what in ("a person's face", "a t-shirt", "a man with a beard", "a plate of food", "a car"):
            a, _ = assess_image(FakeClient(out(what_is_it=what, is_surface=False, confidence=0)), b"img", "image/jpeg")
            self.assertFalse(a.surface, what)
            self.assertEqual(a.confidence, 0.0)

    def test_a_confident_wrong_answer_is_still_caught_by_the_subject(self):
        # the model claims a surface with high confidence while naming a face or a shirt
        for what in ("face", "selfie of a man", "blue t-shirt", "beard", "a dog on a sofa", "screenshot of a chat"):
            a, _ = assess_image(FakeClient(out(what_is_it=what, confidence=0.95)), b"img", "image/jpeg")
            self.assertFalse(a.surface, what)

    def test_painted_things_are_not_blocked_by_the_filter(self):
        for what in ("a cracked bedroom wall", "ceiling with a damp stain", "a living room with white walls",
                     "exterior wall of a house", "stairwell wall", "wall behind a sofa"):
            self.assertTrue(from_vision_output(json.loads(out(what_is_it=what))).surface, what)

    def test_an_old_style_answer_without_the_new_fields_still_works(self):
        raw = {"condition_level": "moderate", "issues": ["peeling"], "confidence": 0.8}
        self.assertTrue(from_vision_output(raw).surface)

    def test_saved_assessments_without_the_new_fields_load(self):
        a = from_dict({"level": "minor", "issues": [], "complexity_flags": [], "confidence": 0.9, "source": "vision"})
        self.assertTrue(a.surface)


class PhotoFlowTests(unittest.TestCase):
    def service(self, assessment):
        service = make_service(reply("Which surfaces?"))
        service.photo_assessor = lambda media_id: assessment
        state = new_state()
        state.greeted = state.service_checked = True
        service.store.save(state)
        return service

    def test_a_non_wall_photo_is_declined_and_not_stored(self):
        service = self.service(ConditionAssessment("good", (), (), 0.0, "vision", False, "a person's face"))
        replies = service.handle(IncomingEvent("p1", "u", type="image", media_id="9"))
        self.assertIn("doesn't show a wall or ceiling", replies[0])
        self.assertNotIn("Thanks for the photo. It looks like", replies[0])
        state = service.store.load("u")
        self.assertIsNone(state.photo_assessment)
        self.assertNotIn("surface_condition", state.verified)
        self.assertEqual(service.store.events(3)[0]["kind"], "photo_not_a_surface")

    def test_the_same_in_malay(self):
        service = self.service(ConditionAssessment("good", (), (), 0.0, "vision", False, "baju"))
        state = service.store.load("u")
        state.lang = "ms"
        service.store.save(state)
        replies = service.handle(IncomingEvent("p1", "u", type="image", media_id="9"))
        self.assertIn("tidak menunjukkan dinding atau siling", replies[0])

    def test_a_real_wall_photo_still_answers_the_condition(self):
        service = self.service(ConditionAssessment("moderate", ("cracks",), (), 0.9, "vision"))
        replies = service.handle(IncomingEvent("p1", "u", type="image", media_id="9"))
        self.assertIn("Thanks for the photo", replies[0])
        self.assertEqual(service.store.load("u").photo_assessment["level"], "moderate")


if __name__ == "__main__":
    unittest.main()
