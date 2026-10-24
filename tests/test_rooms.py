"""More than one room in a job."""
import json
import unittest
from pathlib import Path

from src import flow, rooms
from src.assistant import handle_message
from src.pricing import compute_quotation
from tests.test_core import FakeClient, reply
from tests.test_malay_orders_voice import CONFIG, FULL, new_state

PRICING = FULL["pricing"]


def chat(state, *messages):
    out = None
    for text in messages:
        out = handle_message(state, text, CONFIG, FakeClient(reply("x?"), reply("x?"), reply("x?")))
    return out


class ReadingRoomsTests(unittest.TestCase):
    def test_two_rooms_in_one_message(self):
        found = rooms.sized_rooms("the master bedroom is 4 by 5 by 3 and the kids room is 3 by 3 by 3", new_state())
        self.assertEqual([(r["name"], r["room_length_m"], r["room_width_m"], r["room_height_m"]) for r in found],
                         [("master bedroom", 4.0, 5.0, 3.0), ("kids room", 3.0, 3.0, 3.0)])

    def test_unclear_units_are_not_guessed(self):
        self.assertEqual(rooms.sized_rooms("living 10 by 12 and kitchen 8 by 9", new_state()), [])

    def test_copies_and_same_again(self):
        self.assertEqual(rooms.copies("3 bedrooms, each 4x4"), 3)
        self.assertEqual(rooms.copies("two rooms each 3 by 3"), 2)
        self.assertEqual(rooms.copies("1 bedroom 4x4"), 0)
        self.assertTrue(rooms.wants_same_again("same for the other bedroom"))
        self.assertFalse(rooms.wants_same_again("same colour please"))

    def test_labels(self):
        self.assertEqual(rooms.label_of("and the kids room is"), "kids room")
        self.assertEqual(rooms.label_of("my master bedroom"), "master bedroom")
        self.assertEqual(rooms.label_of("walls 4x4x3"), "")


class RoomFlowTests(unittest.TestCase):
    def test_two_rooms_at_the_start(self):
        state = new_state()
        chat(state, "the master bedroom is 4 by 5 by 3 and the kids room is 3 by 3 by 3, walls")
        v = state.verified
        self.assertEqual((v["room_length_m"], v["room_width_m"], v["room_height_m"], v["room_name"]),
                         (4.0, 5.0, 3.0, "master bedroom"))
        self.assertEqual(len(v["extra_rooms"]), 1)
        self.assertEqual(v["extra_rooms"][0]["name"], "kids room")

    def test_three_bedrooms_each_the_same(self):
        state = new_state()
        out = chat(state, "I have 3 bedrooms, each 4x4x3, walls")
        self.assertEqual(len(state.verified["extra_rooms"]), 2)
        self.assertEqual(state.verified["room_length_m"], 4.0)
        self.assertIn("3 rooms", out.reply)

    def test_a_room_without_a_height_shares_the_first_ones(self):
        state = new_state()
        chat(state, "living room 5 by 4 and kitchen 3 by 3, walls", "height 2.8")
        self.assertEqual(state.verified["room_height_m"], 2.8)
        self.assertEqual(state.verified["extra_rooms"][0]["room_height_m"], 2.8)

    def test_another_room_after_the_first(self):
        state = new_state()
        state.greeted = state.service_checked = True
        state.verified.update({"surfaces": ["walls"], "room_length_m": 4.0, "room_width_m": 4.0, "room_height_m": 3.0,
                               "room_name": "living room"})
        chat(state, "also the kitchen 3x3x2.5")
        self.assertEqual(state.verified["room_length_m"], 4.0)                     # the first room is untouched
        self.assertEqual(state.verified["extra_rooms"][0]["room_height_m"], 2.5)
        chat(state, "same for the other bedroom")
        self.assertEqual(len(state.verified["extra_rooms"]), 2)

    def test_a_correction_is_not_another_room(self):
        state = new_state()
        state.greeted = state.service_checked = True
        state.verified.update({"surfaces": ["walls"], "room_length_m": 4.0, "room_width_m": 4.0, "room_height_m": 3.0})
        chat(state, "sorry I meant 5 x 5")
        self.assertEqual(state.verified["room_length_m"], 5.0)
        self.assertNotIn("extra_rooms", state.verified)

    def test_recap_lists_every_room(self):
        state = new_state()
        state.verified.update({"surfaces": ["walls"], "room_length_m": 4.0, "room_width_m": 5.0, "room_height_m": 3.0,
                               "room_name": "master bedroom",
                               "extra_rooms": [{"name": "kids room", "room_length_m": 3.0, "room_width_m": 3.0,
                                                "room_height_m": 3.0}]})
        recap = flow.recap(state)
        self.assertIn("Room: 4 m long", recap)
        self.assertIn("Room 2 (kids room): 3 m long, 3 m wide, 3 m high", recap)


class RoomPricingTests(unittest.TestCase):
    base = {"surfaces": ["walls", "ceiling"], "room_length_m": 4.0, "room_width_m": 5.0, "room_height_m": 3.0,
            "surface_condition": "good", "paint_tier": "standard"}

    def test_areas_add_up(self):
        one = compute_quotation(dict(self.base), PRICING)
        two = compute_quotation({**self.base, "extra_rooms": [
            {"name": "", "room_length_m": 3.0, "room_width_m": 3.0, "room_height_m": 3.0}]}, PRICING)
        self.assertEqual(one.inputs["wall_area_m2"], 54.0)
        self.assertEqual(two.inputs["wall_area_m2"], 54.0 + 36.0)
        self.assertEqual(two.inputs["ceiling_area_m2"], 20.0 + 9.0)
        self.assertEqual(two.inputs["rooms"], 2)
        self.assertGreater(float(two.total), float(one.total))

    def test_a_missing_height_uses_the_first_rooms(self):
        quote = compute_quotation({**self.base, "extra_rooms": [
            {"name": "", "room_length_m": 3.0, "room_width_m": 3.0, "room_height_m": None}]}, PRICING)
        self.assertEqual(quote.inputs["wall_area_m2"], 54.0 + 36.0)


if __name__ == "__main__":
    unittest.main()
