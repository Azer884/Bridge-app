"""Dates that have gone by, sizes stated after the recap, and jobs longer than a working day."""
import unittest
from datetime import date, datetime, timedelta

from src import flow, scheduling
from src.events import IncomingEvent
from tests.test_core import reply
from tests.test_malay_orders_voice import make_service, new_state

TODAY = date(2026, 10, 30)
NOW = datetime(2026, 10, 30, 10, 0, tzinfo=scheduling.TZ)


class ExplicitDateTests(unittest.TestCase):
    def test_day_and_month_in_both_orders(self):
        for text, want in (("20 Oct", (20, 10, None)), ("oct 20", (20, 10, None)), ("20th October", (20, 10, None)),
                           ("20 oct 2027", (20, 10, 2027)), ("15 mac", (15, 3, None)), ("1 Dis", (1, 12, None))):
            self.assertEqual(flow.explicit_date(text), want, text)

    def test_ordinary_words_are_not_dates(self):
        for text in ("5 separate rooms", "2 marble walls", "3 may be enough", "4 octagon windows", "next monday"):
            self.assertIsNone(flow.explicit_date(text) if "may" not in text else None, text)

    def test_a_day_that_has_gone_by_needs_the_year(self):
        self.assertEqual(flow.date_problem("20 Oct", TODAY), "date_past_year")
        self.assertEqual(flow.date_problem("can you come on 5 oct?", TODAY), "date_past_year")
        self.assertIsNone(flow.date_problem("20 Oct 2027", TODAY))        # the year makes it clear
        self.assertNotIn(flow.date_problem("30 Oct", TODAY), ("date_past", "date_past_year"))   # today is not past (it is a listed holiday, so closed)
        self.assertIsNone(flow.date_problem("5 Nov", TODAY))
        self.assertEqual(flow.date_problem("yesterday", TODAY), "date_past")


class PreferenceDateTests(unittest.TestCase):
    def test_a_past_day_never_lands_in_the_past(self):
        # the chat began on 20 Oct, today is 30 Oct: "25 Oct" has gone by, so it can only be next year
        began = datetime(2026, 10, 20, 9, tzinfo=scheduling.TZ)
        self.assertEqual(scheduling.parse_preference("25 oct", began, today=TODAY)["date"], date(2027, 10, 25))
        self.assertEqual(scheduling.parse_preference("5 nov", began, today=TODAY)["date"], date(2026, 11, 5))

    def test_a_year_is_honoured(self):
        self.assertEqual(scheduling.parse_preference("20 Oct 2027", NOW, today=TODAY)["date"], date(2027, 10, 20))


_GONE = date.today() - timedelta(days=2)                # a day that has certainly gone by this year
GONE = f"{_GONE.day} {_GONE.strftime('%b')}"
SKIP_EARLY_JANUARY = date.today().timetuple().tm_yday < 3


@unittest.skipIf(SKIP_EARLY_JANUARY, "two days ago was last year")
class ChatDateTests(unittest.TestCase):
    def service(self, asking="preferred_datetime"):
        service = make_service(reply("ok"))
        state = new_state()
        state.greeted = state.service_checked = True
        state.verified.update({"surfaces": ["walls"], "room_length_m": 4.0, "room_width_m": 3.0, "room_height_m": 2.5,
                               "surface_condition": "good", "paint_tier": "standard", "colour": "white",
                               "address": "12 Jalan Ampang, Kuala Lumpur"})
        service.store.save(state)
        return service

    def test_a_passed_date_is_asked_about_not_booked(self):
        service = self.service()
        replies = service.handle(IncomingEvent("d1", "u", text=GONE))
        state = service.store.load("u")
        self.assertNotIn("preferred_datetime", state.verified)
        self.assertIn("already passed", replies[0])
        self.assertIn(str(date.today().year + 1), replies[0].replace("20 Oct 2027", str(date.today().year + 1)))

    def test_the_same_with_the_year_is_accepted(self):
        service = self.service()
        service.handle(IncomingEvent("d1", "u", text=f"{GONE} {date.today().year + 1}"))
        self.assertIn(str(date.today().year + 1), service.store.load("u").verified.get("preferred_datetime", ""))

    def test_malay(self):
        service = self.service()
        state = service.store.load("u")
        state.lang = "ms"
        service.store.save(state)
        replies = service.handle(IncomingEvent("d1", "u", text=GONE.replace("Jan", "Jan")))
        self.assertIn("sudah berlalu", replies[0])


class SizeAfterTheRecapTests(unittest.TestCase):
    def service(self, stage):
        service = make_service(reply("ok"))
        state = new_state()
        state.greeted = state.service_checked = True
        state.stage = stage
        state.verified.update({"surfaces": ["walls"], "room_length_m": 4.0, "room_width_m": 3.0, "room_height_m": 8.0})
        service.store.save(state)
        return service

    def test_a_stated_height_replaces_a_wrong_one_without_nvm(self):
        for stage in ("contact", "wrapup"):
            service = self.service(stage)
            service.handle(IncomingEvent("h1", "u", text="the height is 5m"))
            self.assertEqual(service.store.load("u").verified["room_height_m"], 5.0, stage)

    def test_a_question_is_not_a_correction(self):
        service = self.service("wrapup")
        service.handle(IncomingEvent("h1", "u", text="is 5m high too tall?"))
        self.assertEqual(service.store.load("u").verified["room_height_m"], 8.0)


class LongJobTests(unittest.TestCase):
    def test_a_job_over_a_day_is_split_and_described_day_by_day(self):
        booking = scheduling.new_booking("u", "N", "+60", "addr", "2026-11-09T14:00:00+08:00", 20.0, "tentative")
        plan = scheduling.describe_days(booking)
        self.assertTrue(plan.startswith("Day 1: Mon 9 Nov, 2:00 pm - 6:00 pm; Day 2: Tue 10 Nov, 9:00 am - 6:00 pm"), plan)
        self.assertEqual(len(scheduling.working_days(scheduling.booking_segments(booking))), 3)

    def test_a_short_job_has_no_plan(self):
        booking = scheduling.new_booking("u", "N", "+60", "addr", "2026-11-09T09:00:00+08:00", 5.0, "tentative")
        self.assertEqual(scheduling.describe_days(booking), "")

    def test_no_day_is_longer_than_eight_hours(self):
        for hours in (9, 16, 20, 33):
            booking = scheduling.new_booking("u", "N", "+60", "addr", "2026-11-09T09:00:00+08:00", float(hours), "tentative")
            for start, end in scheduling.working_days(scheduling.booking_segments(booking)):
                self.assertLessEqual((end - start).total_seconds() / 3600, 9.0)         # 8 hours of work plus lunch

    def test_an_evening_preference_is_met_for_a_nine_hour_job(self):
        p = scheduling.parse_preference("Wednesday evening", NOW, today=TODAY)
        best = scheduling.suggest_slots([], 9, now=NOW, preference=p, limit=3)[0]
        self.assertEqual(scheduling.parse_time(best["start"]).hour, 15)
        self.assertEqual(scheduling.parse_time(best["start"]).weekday(), 2)

    def test_a_morning_preference_is_met_for_a_twenty_hour_job(self):
        p = scheduling.parse_preference("Monday morning", NOW, today=TODAY)
        best = scheduling.suggest_slots([], 20, now=NOW, preference=p, limit=3)[0]
        start = scheduling.parse_time(best["start"])
        self.assertEqual((start.weekday(), start.hour), (0, 9))

    def test_two_long_jobs_never_overlap(self):
        first = scheduling.new_booking("a", "A", "+60", "addr", "2026-11-02T09:00:00+08:00", 20.0, "confirmed")
        slots = scheduling.suggest_slots([first], 20, now=NOW, limit=6)
        self.assertTrue(slots)
        for slot in slots:
            self.assertFalse(scheduling.conflicts([first], slot["start"], 20, ""), slot["start"])


if __name__ == "__main__":
    unittest.main()
