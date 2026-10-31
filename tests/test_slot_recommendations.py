"""The calendar's suggested times: working days only, no public holidays, the day the customer asked for first, a spread of days."""
import unittest
from datetime import datetime

from src import scheduling as s

TZ = s.TZ
NOW = datetime(2026, 11, 1, 20, 0, tzinfo=TZ)                 # Sunday night; Fri 6 Nov 2026 is a public holiday (Perak)


def booked(name, address, when, hours):
    return s.new_booking(name.lower(), name, "1", address, when, hours, "confirmed")


BOOKINGS = [booked("Ali", "12 Jalan Ampang, 50450 Kuala Lumpur", datetime(2026, 11, 3, 9, 0, tzinfo=TZ), 4),
            booked("Siti", "5 Jalan SS2/3, 47300 Petaling Jaya", datetime(2026, 11, 4, 14, 0, tzinfo=TZ), 3)]


def suggest(hours=4, text=None, address="Shah Alam", bookings=BOOKINGS, **kw):
    pref = s.parse_preference(text, NOW, today=NOW.date()) if text else None
    return s.suggest_slots(bookings, hours, address, now=NOW, preference=pref, **kw)


def days(slots):
    return [s.parse_time(x["start"]).date().isoformat() for x in slots]


class HolidayTests(unittest.TestCase):
    def test_a_public_holiday_is_never_suggested(self):
        for text in (None, "6 Nov", "Friday"):
            self.assertNotIn("2026-11-06", days(suggest(2, text)), text)

    def test_a_long_job_skips_the_holiday_and_the_weekend(self):
        slot = suggest(10)[0]
        start, end = s.parse_time(slot["start"]), s.parse_time(slot["end"])
        self.assertEqual(start.date().isoformat(), "2026-11-05")           # Thursday: Friday is a holiday
        self.assertEqual(end.date().isoformat(), "2026-11-09")             # so the job ends on Monday

    def test_weekends_are_never_suggested(self):
        for slot in suggest(4):
            self.assertLess(s.parse_time(slot["start"]).weekday(), 5)


class PreferenceTests(unittest.TestCase):
    def test_the_day_asked_for_comes_first_and_is_labelled(self):
        top = suggest(4, "Thursday morning")[0]
        start = s.parse_time(top["start"])
        self.assertEqual((start.strftime("%a"), start.hour), ("Thu", 9))
        self.assertIn("asked for", top["reason"])

    def test_a_morning_on_the_wrong_day_does_not_claim_to_match(self):
        for slot in suggest(4, "Thursday morning"):
            if s.parse_time(slot["start"]).weekday() != 3:
                self.assertNotIn("asked for", slot["reason"])

    def test_a_wrong_day_never_beats_the_right_day(self):
        slots = suggest(2, "Wednesday 2pm")
        wed = [x for x in slots if s.parse_time(x["start"]).weekday() == 2]
        other = [x for x in slots if s.parse_time(x["start"]).weekday() != 2]
        self.assertTrue(wed and other)
        self.assertGreater(min(x["score"] for x in wed), max(x["score"] for x in other))

    def test_a_day_beyond_the_usual_window_is_still_looked_at(self):
        slots = suggest(2, "30 Nov")
        self.assertIn("2026-11-30", days(slots))
        self.assertEqual(s.parse_time(slots[0]["start"]).date().isoformat(), "2026-11-30")


class SpreadTests(unittest.TestCase):
    def test_six_suggestions_are_not_two_days_of_the_same_choice(self):
        slots = suggest(2, None, address="Cheras")
        counts = {}
        for day in days(slots):
            counts[day] = counts.get(day, 0) + 1
        self.assertLessEqual(max(counts.values()), 2)
        self.assertGreaterEqual(len(counts), 3)

    def test_suggestions_never_clash_with_a_booking(self):
        for slot in suggest(4, None, address="12 Jalan Ampang, 50450 Kuala Lumpur"):
            self.assertFalse(s.conflicts(BOOKINGS, slot["start"], 4, "12 Jalan Ampang, 50450 Kuala Lumpur"))


class SlotHoursTests(unittest.TestCase):
    def test_every_slot_says_the_working_hours_of_the_job(self):
        for hours in (2, 4, 10):
            for slot in suggest(hours):
                self.assertEqual(slot["hours"], hours)

    def test_a_long_job_slot_spans_days_but_keeps_its_working_hours(self):
        slot = suggest(10)[0]
        span = (s.parse_time(slot["end"]) - s.parse_time(slot["start"])).total_seconds() / 3600
        self.assertGreater(span, 24)                                    # days apart on the clock
        self.assertEqual(slot["hours"], 10)                             # the form must use this, not the clock span


if __name__ == "__main__":
    unittest.main()
