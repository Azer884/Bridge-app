"""Fixes found by replaying a real phone call: spelled-out sizes that repeat a known one, and "three AM"."""
import unittest

from src import flow
from src.events import IncomingEvent
from tests.test_core import reply
from tests.test_malay_orders_voice import make_service, new_state


def _service(**verified):
    service = make_service(*[reply("ok")] * 10)
    state = new_state()
    state.greeted = state.service_checked = True
    state.verified.update({"surfaces": ["one wall"], **verified})
    service.store.save(state)
    return service


class SizeRepeatingAKnownOneTests(unittest.TestCase):
    def test_eight_by_four_after_the_length_gives_the_height(self):
        service = _service(room_length_m=8.0)
        service.handle(IncomingEvent("a1", "u", text="It's eight by four meters."))
        verified = service.store.load("u").verified
        self.assertEqual((verified["room_length_m"], verified["room_height_m"]), (8.0, 4.0))

    def test_two_sentences_with_a_repeated_figure(self):
        service = _service(room_length_m=8.0)
        service.handle(IncomingEvent("a1", "u", text="It's eight meter. Four meters."))
        self.assertEqual(service.store.load("u").verified["room_height_m"], 4.0)


class ClockWordsTests(unittest.TestCase):
    def test_three_am_is_a_closed_hour(self):
        self.assertEqual(flow.date_problem("Three AM."), "date_closed")
        self.assertEqual(flow.date_problem("seven pm"), "date_closed")
        self.assertIsNone(flow.date_problem("ten am on a weekday"))

    def test_three_am_is_not_read_as_a_height(self):
        service = _service(room_length_m=8.0)
        replies = service.handle(IncomingEvent("a1", "u", text="Three AM."))
        self.assertNotIn("room_height_m", service.store.load("u").verified)
        self.assertIn("Monday to Friday", replies[0])


if __name__ == "__main__":
    unittest.main()
