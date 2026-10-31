"""A restarted chat starts clean: no trade, no photo from the old job, and plain answers are read the right way."""
import unittest

from src import flow
from src.events import IncomingEvent
from tests.test_core import reply
from tests.test_two_trades import UID, mixed, say


class RestartTests(unittest.TestCase):
    def painted(self):
        """A chat that has already been a painting job with a photo."""
        svc = mixed()
        say(svc, "I want to paint my bedroom wall", 1)
        state = svc.store.load(UID)
        state.last_photo_id = "old-photo"
        svc.store.save(state)
        return svc

    def test_start_over_forgets_the_trade_and_the_photo(self):
        svc = self.painted()
        out = say(svc, "start over", 2)
        state = svc.store.load(UID)
        self.assertEqual((state.trade, state.last_photo_id), ("", ""))
        self.assertIn("painting or aircon", out)

    def test_services_after_a_restart_name_every_trade(self):
        svc = self.painted()
        say(svc, "start over", 2)
        out = say(svc, "What services do you provide", 3)
        self.assertIn("aircon", out.lower())
        self.assertIn("paint", out.lower())

    def test_no_photo_means_the_problem_is_not_a_photo(self):
        svc = self.painted()
        say(svc, "start over", 2)
        say(svc, "Hello i have a broken air conditioner", 3)
        state = svc.store.load(UID)
        self.assertEqual(state.trade, "aircon")
        self.assertNotEqual(state.verified.get("aircon_issue"), "see the customer's photo")


class AirconAnswerTests(unittest.TestCase):
    def chat(self, *steps):
        svc = mixed()
        outs = [say(svc, text, n) for n, text in enumerate(steps, 1)]
        return svc.store.load(UID), outs

    def test_just_one_is_one_unit(self):
        state, outs = self.chat("I need my aircon serviced", "general service", "Just one")
        self.assertEqual(state.verified.get("unit_count"), "1")
        self.assertIn("horsepower", outs[-1].lower())

    def test_a_bare_decimal_is_the_horsepower_never_the_unit_count(self):
        state, outs = self.chat("I need my aircon serviced", "general service", "Just one", "2.0")
        self.assertEqual(state.verified.get("horsepower"), "2.0 HP")
        self.assertEqual(state.verified.get("unit_count"), "1")
        self.assertNotIn("How many aircon units", outs[-1])

    def test_a_bare_decimal_is_the_horsepower_even_while_units_are_still_missing(self):
        state, _ = self.chat("I need my aircon serviced", "general service", "2.0")
        self.assertEqual(state.verified.get("horsepower"), "2.0 HP")
        self.assertNotIn("unit_count", state.verified)


if __name__ == "__main__":
    unittest.main()
