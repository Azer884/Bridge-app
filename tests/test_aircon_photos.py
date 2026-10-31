"""Photos of aircon units: the vision model reads the unit and what it sees; fixed lists and the technician decide the rest."""
import json
import unittest

from src import assessment, vision
from src.assessment import ConditionAssessment, combine, from_dict
from src.events import IncomingEvent
from tests.test_core import FakeClient
from tests.test_two_trades import UID, mixed, say


def model_says(**fields):
    base = {"what_is_it": "wall-mounted aircon", "is_unit": True, "unit_type": "wall_mounted", "condition_level": "moderate",
            "issues": ["water_stains", "dirty_filter"], "confidence": 0.9}
    return json.dumps({**base, **fields})


class ParseTests(unittest.TestCase):
    def test_a_unit_photo_keeps_only_allowed_words(self):
        result = assessment.from_aircon_output(json.loads(model_says(issues=["dirty_filter", "haunted", "rust"], unit_type="spaceship")))
        self.assertEqual(result.issues, ("dirty_filter", "rust"))
        self.assertEqual(result.details, {})                      # an unknown unit type is dropped
        self.assertTrue(result.surface)

    def test_the_unit_type_is_kept_when_it_is_allowed(self):
        result = assessment.from_aircon_output(json.loads(model_says()))
        self.assertEqual(result.details, {"unit_type": "wall_mounted"})
        self.assertEqual(result.level, "moderate")

    def test_a_photo_that_is_not_a_unit_has_no_confidence(self):
        result = assessment.from_aircon_output(json.loads(model_says(is_unit=False, what_is_it="a dog")))
        self.assertFalse(result.surface)
        self.assertEqual(result.confidence, 0.0)

    def test_numbers_the_model_adds_are_ignored(self):
        result = assessment.from_aircon_output(json.loads(model_says(horsepower=2.5, unit_count=9, price=99)))
        self.assertNotIn("horsepower", str(result))
        self.assertNotIn("99", str(result))

    def test_an_unusable_level_is_refused(self):
        self.assertIsNone(assessment.from_aircon_output({"is_unit": True, "condition_level": "wild"}))

    def test_details_survive_saving_and_merging(self):
        a = assessment.from_aircon_output(json.loads(model_says()))
        saved = from_dict(json.loads(json.dumps(combine(a).__dict__ | {"issues": list(a.issues), "complexity_flags": []})))
        self.assertEqual(saved.details, {"unit_type": "wall_mounted"})


class PromptTests(unittest.TestCase):
    def test_the_trade_picks_the_instruction_and_the_parser(self):
        client = FakeClient(model_says())
        result, _ = vision.assess_image(client, b"x" * 100, "image/jpeg", trade="aircon")
        system = client.calls[0][0]["content"]
        self.assertIn("air conditioner", system)
        self.assertNotIn("paint the walls", system)
        self.assertEqual(result.details["unit_type"], "wall_mounted")

    def test_painting_is_still_the_default(self):
        client = FakeClient(json.dumps({"what_is_it": "wall", "is_surface": True, "condition_level": "good", "issues": [],
                                        "complexity_flags": [], "confidence": 0.9}))
        vision.assess_image(client, b"x" * 100, "image/jpeg")
        self.assertIn("paint the walls", client.calls[0][0]["content"])


class ChatPhotoTests(unittest.TestCase):
    def photo(self, svc, result, n=5):
        calls = []

        def assessor(media_id, trade="painting"):
            calls.append(trade)
            if isinstance(result, Exception):
                raise result
            return result

        svc.photo_assessor = assessor
        out = svc.handle(IncomingEvent(f"p{n}", UID, type="image", media_id=f"media{n}", text=""))
        return (out[0] if out else ""), calls

    def start(self):
        svc = mixed()
        say(svc, "my aircon needs a service", 1)
        return svc

    def unit(self, **kw):
        return assessment.from_aircon_output(json.loads(model_says(**kw)))

    def test_the_model_is_asked_about_an_aircon_not_a_wall(self):
        svc = self.start()
        _out, calls = self.photo(svc, self.unit())
        self.assertEqual(calls, ["aircon"])

    def test_the_customer_hears_what_was_seen(self):
        svc = self.start()
        out, _ = self.photo(svc, self.unit())
        self.assertIn("wall-mounted unit", out)
        self.assertIn("water stains", out)
        self.assertIn("technician will confirm", out)

    def test_the_photo_answers_the_problem_question_and_is_saved_for_pricing(self):
        svc = self.start()
        self.photo(svc, self.unit())
        state = svc.store.load(UID)
        self.assertIn("aircon_issue", state.verified)
        self.assertEqual(from_dict(state.photo_assessment).level, "moderate")

    def test_a_photo_of_something_else_is_not_used(self):
        svc = self.start()
        out, _ = self.photo(svc, self.unit(is_unit=False, what_is_it="a sofa"))
        self.assertIn("doesn't show an aircon unit", out)
        self.assertIsNone(svc.store.load(UID).photo_assessment)

    def test_a_model_that_is_down_still_passes_the_photo_to_the_technician(self):
        svc = self.start()
        out, _ = self.photo(svc, RuntimeError("endpoint down"))
        self.assertIn("passed your photo to our technician", out)

    def test_a_low_confidence_reading_is_not_trusted(self):
        svc = self.start()
        out, _ = self.photo(svc, self.unit(confidence=0.3))
        self.assertIn("passed your photo to our technician", out)
        self.assertIsNone(svc.store.load(UID).photo_assessment)

    def test_a_severe_photo_sends_the_job_to_a_person_when_priced(self):
        svc = mixed()
        say(svc, "my aircon needs a service", 1)
        self.photo(svc, self.unit(condition_level="severe", issues=["damaged_casing"]))
        state = svc.store.load(UID)
        state.verified.update({"service_type": "general service", "unit_count": "1", "horsepower": "1.0 HP"})
        quote = svc._price(state)
        self.assertEqual(quote.status, "needs_inspection")
        self.assertTrue(any("breakdown" in f or "diagnostic" in f for f in quote.flags))

    def test_a_painting_chat_still_uses_the_wall_model(self):
        svc = mixed()
        say(svc, "I want to paint my wall", 1)
        _out, calls = self.photo(svc, ConditionAssessment("good", (), (), 0.9, "vision", True, "wall"), n=6)
        self.assertEqual(calls, ["painting"])       # the wall model, as before


if __name__ == "__main__":
    unittest.main()
