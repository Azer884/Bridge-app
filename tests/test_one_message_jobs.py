"""Everything in one message: the address, the date and the condition are pulled apart, not glued together."""
import unittest
from datetime import date, timedelta

from src.answers import address_in, condition_clause
from src.events import IncomingEvent
from tests.test_core import reply
from tests.test_malay_orders_voice import make_service, new_state

_GONE = date.today() - timedelta(days=2)
GONE = f"{_GONE.day} {_GONE.strftime('%b')}"


class AddressAndConditionTests(unittest.TestCase):
    def test_the_address_stops_before_the_date_and_the_condition(self):
        cases = {
            "walls 4x4x3 standard white 12 Jalan Ampang Kuala Lumpur 20 oct no damage": "12 Jalan Ampang Kuala Lumpur",
            "12 Jalan Ampang KL 31 oct no damage": "12 Jalan Ampang KL",
            "dinding 5x4x3 standard putih 12 Jalan Ampang KL 5 okt tiada kerosakan": "12 Jalan Ampang KL",
            "at 12 Jalan Ampang, Taman Melati, KL saturday morning": "12 Jalan Ampang, Taman Melati, KL",
        }
        for text, want in cases.items():
            self.assertEqual(address_in(text), want, text)

    def test_the_town_and_state_stay_in_the_address(self):
        self.assertEqual(address_in("12 Jalan Setia, Johor Bahru, Johor"), "12 Jalan Setia, Johor Bahru, Johor")
        self.assertEqual(address_in("5 Jalan Mawar, 43200 Cheras, Selangor"), "5 Jalan Mawar, 43200 Cheras, Selangor")

    def test_only_the_condition_words_are_kept(self):
        self.assertEqual(condition_clause("walls 4x4x3 standard white 12 Jalan Ampang Kuala Lumpur 20 oct no damage"), "no damage")
        self.assertEqual(condition_clause("paint is peeling and some damp"), "paint is peeling and some damp")
        self.assertEqual(condition_clause("cracks near the window"), "cracks near the window")


class ChatTests(unittest.TestCase):
    def service(self):
        return make_service(reply("ok"), reply("ok"), reply("ok"))

    def test_a_full_first_message_is_split_into_fields(self):
        service = self.service()
        service.handle(IncomingEvent("a", "u", text="walls 4x4x3 standard white 12 Jalan Ampang Kuala Lumpur no damage"))
        v = service.store.load("u").verified
        self.assertEqual(v["address"], "12 Jalan Ampang Kuala Lumpur")
        self.assertEqual(v["surface_condition"], "no damage")
        self.assertEqual(v["paint_tier"], "standard")
        self.assertEqual((v["room_length_m"], v["room_width_m"], v["room_height_m"]), (4.0, 4.0, 3.0))

    def test_a_date_that_has_gone_by_in_the_first_message_is_explained(self):
        if date.today().timetuple().tm_yday < 3:
            self.skipTest("two days ago was last year")
        service = self.service()
        out = service.handle(IncomingEvent("a", "u", text=f"walls 4x4x3 standard white 12 Jalan Ampang Kuala Lumpur {GONE} no damage"))
        self.assertIn("already passed", out[0])
        self.assertNotIn("preferred_datetime", service.store.load("u").verified)

    def correcting(self, message, height=5.0):
        service = self.service()
        state = new_state()
        state.greeted = state.service_checked = state.contact_confirmed = True
        state.stage = "wrapup"
        state.verified.update({"surfaces": ["walls"], "room_length_m": 4.0, "room_width_m": 3.0, "room_height_m": height})
        state.last_field = "room_height_m"
        service.store.save(state)
        service.handle(IncomingEvent("c", "u", text=message))
        return service.store.load("u").verified["room_height_m"]

    def test_x_not_y_keeps_x(self):
        for message in ("sorry its 2.7 not 5", "its 2.7m high not 5m", "2.7 not 5", "height is 2.7, not 5", "tinggi 2.7 bukan 5"):
            self.assertEqual(self.correcting(message), 2.7, message)

    def test_yes_to_meters_or_feet_asks_once_more(self):
        service = self.service()
        service.handle(IncomingEvent("a", "u", text="walls and ceiling 12x10x3 cream"))
        out = service.handle(IncomingEvent("b", "u", text="yes"))
        self.assertIn("meters or in feet", out[0])
        service.handle(IncomingEvent("c", "u", text="feet"))
        v = service.store.load("u").verified
        self.assertAlmostEqual(v["room_length_m"], 3.658, places=2)
        self.assertEqual(v["room_height_m"], 3.0)                    # a 3 ft ceiling is not a room: the 3 was metres


if __name__ == "__main__":
    unittest.main()
