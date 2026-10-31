"""A day or hour the crew does not work is explained, and a new time is never read as a new size."""
import unittest

from src import flow, scheduling
from src.events import IncomingEvent
from tests.test_core import reply
from tests.test_malay_orders_voice import make_service, new_state


def job(**extra):
    service = make_service(*[reply("ok")] * 6)
    state = new_state()
    state.greeted = state.service_checked = True
    state.stage = "job"
    state.verified.update({"surfaces": ["walls"], "room_length_m": 4.0, "room_width_m": 3.0, "room_height_m": 2.0, "paint_tier": "premium",
                           "colour": "white", **extra})
    service.store.save(state)
    return service


class WorkingTimeTests(unittest.TestCase):
    def test_what_is_outside_the_crews_hours(self):
        for text in ("Actually can you do 3 Am sunday", "I'm free Sunday afternoon if you guys are working then",
                     "monday 6pm", "Ahad pagi", "Saturday 10am", "weekends are good for me", "three AM on Monday",
                     "hari raya", "25 Dec", "Sabtu pagi", "I'll be three three AM"):
            self.assertEqual(flow.date_problem(text), "date_closed", text)

    def test_what_is_inside_them(self):
        for text in ("monday 10am", "5:30pm monday", "any day except sunday", "3 meters", "9am"):
            self.assertIsNone(flow.date_problem(text), text)

    def test_the_hours_are_said_from_the_calendar_rules(self):
        self.assertEqual(scheduling.working_hours_text("en"), "Monday to Friday 9 am to 6 pm")
        self.assertIn("Isnin hingga Jumaat", scheduling.working_hours_text("ms"))


class ChatTests(unittest.TestCase):
    def test_a_job_in_another_country_is_refused_and_not_stored(self):
        service = job(surface_condition="no damage", preferred_datetime="monday 10am")
        out = service.handle(IncomingEvent("a", "u", text="the house is in Jakarta, Indonesia"))
        self.assertIn("not in Malaysia", out[0])
        self.assertNotIn("address", service.store.load("u").verified)

    def test_a_closed_time_gets_the_hours_and_is_not_stored(self):
        service = job(surface_condition="no damage", address="12 Jalan Ampang Kuala Lumpur")      # only the date is still open
        out = service.handle(IncomingEvent("a", "u", text="I'm free Sunday afternoon if you guys are working then"))
        self.assertIn("Our crew works Monday to Friday 9 am to 6 pm, and not on weekends or public holidays", out[0])
        self.assertNotIn("preferred_datetime", service.store.load("u").verified)

    def test_a_new_time_is_not_read_as_a_new_size(self):
        service = job(preferred_datetime="tuesday 10am")
        service.handle(IncomingEvent("a", "u", text="Actually can you do 3 Am sunday"))
        v = service.store.load("u").verified
        self.assertEqual(v["room_length_m"], 4.0)                 # the old bug: "updated the room length to 3 meters"
        self.assertEqual(v["preferred_datetime"], "tuesday 10am")

    def test_a_good_new_time_replaces_the_old_one(self):
        service = job(preferred_datetime="tuesday 10am")
        service.handle(IncomingEvent("a", "u", text="Actually can you do friday 3pm"))
        v = service.store.load("u").verified
        self.assertEqual(v["room_length_m"], 4.0)
        self.assertEqual(v["preferred_datetime"], "friday 3pm")

    def test_a_long_message_with_a_closed_time_is_explained_and_not_taken_as_the_address(self):
        service = job(surface_condition="no damage", preferred_datetime="tommorow")      # the address is what is still open
        out = service.handle(IncomingEvent("a", "u", text="tommorow morning ,i m a morning guy maybe at 3 am"))
        self.assertIn("Our crew works", out[0])
        v = service.store.load("u").verified
        self.assertNotIn("address", v)                                   # the old bug stored this sentence as the address
        self.assertEqual(v["preferred_datetime"], "tommorow")

    def test_a_time_with_a_comma_and_a_digit_is_not_an_address(self):
        from src.answers import is_address
        self.assertFalse(is_address("tommorow morning ,i m a morning guy maybe at 3 am"))
        self.assertTrue(is_address("12 Jalan Ampang, Kuala Lumpur"))
        self.assertTrue(is_address("no 8 Jalan Mawar 3, Seksyen 7, 40000 Shah Alam"))

    def test_a_real_size_correction_still_works(self):
        service = job(preferred_datetime="tuesday 10am")
        service.handle(IncomingEvent("a", "u", text="actually its 3m long"))
        self.assertEqual(service.store.load("u").verified["room_length_m"], 3.0)


if __name__ == "__main__":
    unittest.main()
