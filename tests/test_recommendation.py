"""A question about which paint to pick is answered, not taken as "no preference"; informal withdrawals are caught."""
import unittest

from src import consent
from src.events import IncomingEvent
from tests.test_core import reply
from tests.test_malay_orders_voice import make_service, new_state


def asking_for_the_paint():
    service = make_service(reply("Noted. What paint quality?"), reply("ok"), reply("ok"))
    state = new_state()
    state.greeted = state.service_checked = True
    state.stage = "job"
    state.verified.update({"surfaces": ["walls", "ceiling"], "room_length_m": 12.0, "room_width_m": 10.0, "room_height_m": 7.0})
    service.store.save(state)
    return service


class PaintRecommendationTests(unittest.TestCase):
    def test_which_one_do_you_recommend_gets_an_answer_and_the_question_again(self):
        for text in ("Which one do you recommend", "No which paint quality do u recommend i didn t choose yey",
                     "what do you suggest for the paint?"):
            service = asking_for_the_paint()
            out = service.handle(IncomingEvent("q", "u", text=text))
            self.assertIn("Most customers choose standard", out[0], text)
            self.assertIn("economy, standard or premium", out[0], text)
            self.assertNotIn("paint_tier", service.store.load("u").verified, text)      # nothing was chosen for them

    def test_you_choose_still_means_no_preference(self):
        service = asking_for_the_paint()
        service.handle(IncomingEvent("q", "u", text="you choose"))
        self.assertEqual(service.store.load("u").verified["paint_tier"], "no preference")

    def test_a_named_tier_is_taken(self):
        service = asking_for_the_paint()
        service.handle(IncomingEvent("q", "u", text="ok premium"))
        self.assertEqual(service.store.load("u").verified["paint_tier"], "premium")


class InformalWithdrawalTests(unittest.TestCase):
    def test_informal_ways_of_saying_no(self):
        for text in ("Nvm dont have my agreement", "you don't have my consent", "no consent", "I never agreed",
                     "I didn't agree", "tak beri kebenaran"):
            self.assertTrue(consent.objects(text), text)

    def test_ordinary_sentences_are_left_alone(self):
        for text in ("I don't have my number", "no preference", "don't have my measurements", "I got my agreement form ready"):
            self.assertFalse(consent.objects(text), text)


if __name__ == "__main__":
    unittest.main()
