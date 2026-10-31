"""Sizes the way a speech-to-text transcript or a person on a call writes them: the same on a call and in the chat."""
import unittest

from src.events import IncomingEvent
from src.grounding import normalise_speech, spoken_sizes
from tests.test_core import reply
from tests.test_malay_orders_voice import make_service, new_state

SAID = [
    "The room is 5 meters long 3 meters wide and 3 meters tall",
    "The room is five meters long, three meters wide, and three meters tall.",
    "The room is 5 m. long, 3 m. wide and 3 m. tall.",
    "The room is five-meter long, three-meter wide, and three-meter tall.",
    "It's five meters in length, three meters in width and three meters in height.",
    "Five meters long. Three meters wide. And three meters tall.",
    "The room is five hundred centimeters long, three hundred centimeters wide and three hundred centimeters tall.",
    "Um, the room is like five meters long, uh, three meters wide and, uh, three meters tall.",
    "The room is three meters wide, five meters long and three meters tall.",
]


def sizes_after(text, channel):
    svc = make_service(*[reply("ok")] * 6)
    state = new_state()
    state.greeted = state.service_checked = True
    state.verified.update({"surfaces": ["walls"]})
    svc.store.save(state)
    svc.handle(IncomingEvent("a", "u", text=text, channel=channel))
    v = svc.store.load("u").verified
    return v.get("room_length_m"), v.get("room_width_m"), v.get("room_height_m")


class NormaliserTests(unittest.TestCase):
    def test_what_speech_writes_becomes_plain_sizes(self):
        self.assertEqual(spoken_sizes("5 m. long"), "5 m long")
        self.assertEqual(spoken_sizes("five-meter wide"), "five meter wide")
        self.assertEqual(spoken_sizes("five meters in length"), "five meters long")
        self.assertEqual(spoken_sizes("two and a half meters"), "2.5 meters")
        self.assertEqual(spoken_sizes("three point five meters"), "3.5 meters")
        self.assertEqual(spoken_sizes("five hundred centimeters"), "500 centimeters")
        self.assertEqual(spoken_sizes("three hundred and fifty centimeters"), "350 centimeters")

    def test_ordinary_text_is_left_alone(self):
        for text in ("I want to paint my room", "4x4x3", "my name is Ali", "a hundred percent sure", "in a hurry"):
            self.assertEqual(spoken_sizes(text), text)


class SameOnACallAndInTheChatTests(unittest.TestCase):
    def test_every_way_of_saying_it_gives_5_by_3_by_3_on_both_channels(self):
        for text in SAID:
            for channel in ("whatsapp", "voice"):
                self.assertEqual(sizes_after(text, channel), (5.0, 3.0, 3.0), f"{channel}: {text}")

    def test_feet_and_halves(self):
        self.assertEqual(sizes_after("The room is sixteen feet long, ten feet wide and nine feet tall.", "voice"),
                         (4.877, 3.048, 2.743))
        self.assertEqual(sizes_after("The room is five and a half meters long, three meters wide and two and a half meters tall.",
                                     "voice"), (5.5, 3.0, 2.5))

    def test_the_list_said_in_pieces_gives_the_same_answer(self):
        svc = make_service(*[reply("ok")] * 6)
        state = new_state()
        state.greeted = state.service_checked = True
        state.verified.update({"surfaces": ["walls"]})
        svc.store.save(state)
        for i, part in enumerate(["The room is 5 meters long", "3 meters wide", "and 3 meters tall"]):
            svc.handle(IncomingEvent(f"s{i}", "u", text=part, channel="voice"))
        v = svc.store.load("u").verified
        self.assertEqual((v["room_length_m"], v["room_width_m"], v["room_height_m"]), (5.0, 3.0, 3.0))


class SpokenPhonesDatesAndStreetsTests(unittest.TestCase):
    def test_phone_numbers_said_as_digit_words(self):
        for said, written in (("zero one two three four five six seven eight nine", "0123456789"),
                              ("oh one two three four five six seven eight nine", "0123456789"),
                              ("my number is zero one two, three four five, six seven eight nine", "my number is 0123456789"),
                              ("plus six zero one two three four five six seven eight nine", "+60123456789"),
                              ("zero one double two three four five six seven", "012234567")):
            self.assertEqual(normalise_speech(said), written)

    def test_short_runs_of_number_words_are_not_phone_numbers(self):
        for text in ("one two three", "I want five walls", "oh five meters", "two or three coats"):
            self.assertEqual(normalise_speech(text), text)

    def test_dates_said_aloud(self):
        self.assertEqual(normalise_speech("the fifth of November at two pm"), "5 November at 2 pm")
        self.assertEqual(normalise_speech("November the fifth"), "November 5")
        self.assertEqual(normalise_speech("twenty first of october"), "21 october")
        self.assertEqual(normalise_speech("Tuesday ten a.m."), "Tuesday 10 am")
        self.assertEqual(normalise_speech("Tuesday at ten AM"), "Tuesday at 10 am")

    def test_five_may_be_enough_is_not_a_date(self):
        self.assertEqual(normalise_speech("five may be enough"), "five may be enough")

    def test_street_numbers_said_aloud(self):
        self.assertEqual(normalise_speech("twelve Jalan Ampang Kuala Lumpur"), "12 Jalan Ampang Kuala Lumpur")
        self.assertEqual(normalise_speech("twenty five Jalan SS two slash three Petaling Jaya"), "25 Jalan SS 2/3 Petaling Jaya")

    def test_a_call_with_the_phone_and_date_said_in_words(self):
        svc = make_service(reply("ok"), reply("ok"), reply("ok"), reply("ok"), reply("ok"), reply("ok"), reply("ok"), reply("ok"))
        state = new_state()
        state.greeted = state.service_checked = True
        state.stage = "contact"
        state.contact_step = "ask_phone"
        state.verified.update({"surfaces": ["walls"], "room_length_m": 5.0, "room_width_m": 3.0, "room_height_m": 3.0,
                               "paint_tier": "standard", "colour": "white", "surface_condition": "good",
                               "address": "12 Jalan Ampang, Kuala Lumpur", "customer_name": "Siti"})
        svc.store.save(state)
        svc.handle(IncomingEvent("p1", "u", text="zero one two three four five six seven eight nine", channel="voice"))
        saved = svc.store.load("u")
        self.assertEqual(saved.verified.get("phone"), "0123456789")


class SpokenTimesTests(unittest.TestCase):
    def test_times_said_aloud(self):
        for said, written in (("half past two", "2:30 pm"), ("half past two in the afternoon", "2:30 pm"),
                              ("quarter to three", "2:45 pm"), ("quarter past nine", "9:15"), ("ten past two", "2:10 pm"),
                              ("Tuesday at two o'clock", "Tuesday at 2:00 pm"), ("at two thirty", "2:30 pm"),
                              ("nine thirty in the morning", "9:30 am"), ("two thirty pm", "2:30 pm"),
                              ("half past ten a.m.", "10:30 am"), ("quarter to one", "12:45")):
            self.assertEqual(normalise_speech(said), written, said)

    def test_ranges_and_sizes_are_not_times(self):
        for text in ("maybe 4 to 5 m", "five to ten meters", "three to four meters wide", "two thirty", "five fifteen meters",
                     "two and a half meters"):
            self.assertNotIn(":", normalise_speech(text), text)

    def test_a_time_said_in_words_is_read_and_a_closed_hour_is_refused(self):
        from src import flow
        self.assertIsNone(flow.date_problem(normalise_speech("Tuesday at half past two")))
        self.assertEqual(flow.date_problem(normalise_speech("Tuesday at half past seven")), "date_closed")
        self.assertIsNotNone(flow.when_in(normalise_speech("Tuesday at half past two"), strict=True))


class SpokenNamesTests(unittest.TestCase):
    def test_names_said_with_sounds_and_phrases_around_them(self):
        from src import contact
        for said, name in (("it's Ali", "Ali"), ("Ali here", "Ali"), ("uh, Ali", "Ali"), ("Ali.", "Ali"), ("it is Ali", "Ali"),
                           ("Ali Hassan please", "Ali Hassan"), ("yeah it's Ali Hassan", "Ali Hassan"), ("ini Ali", "Ali"),
                           ("Ali la", "Ali"), ("um, it's Siti Aminah, thanks", "Siti Aminah")):
            self.assertEqual(contact.find_name(said, allow_bare=True), name, said)

    def test_the_introductions_before_a_name(self):
        from src.answers import explicit_name
        self.assertEqual(explicit_name("I'm Ahmad Faiz speaking"), "Ahmad Faiz")
        self.assertEqual(explicit_name("this is Ali speaking"), "Ali")
        self.assertEqual(explicit_name("my name is um Ali"), "Ali")

    def test_a_day_or_a_paint_is_not_taken_for_a_name_in_the_job(self):
        from src.answers import explicit_name
        for text in ("It's Thursday", "it's premium", "it's tomorrow"):
            self.assertIsNone(explicit_name(text), text)


class CallReadBackTests(unittest.TestCase):
    def test_a_phone_number_is_read_digit_by_digit(self):
        from voice_worker.backend import spoken
        self.assertIn("0 1 2, 3 4 5, 6 7 8 9", spoken(["Noted under Ali (0123456789)."]))
        self.assertIn("plus 6 0", spoken(["Noted under Siti (+60111222333)."]))

    def test_sizes_dates_and_prices_are_not_read_as_phone_numbers(self):
        from voice_worker.backend import spoken
        self.assertEqual(spoken(["The room is 5 by 3 by 3 meters."]), "The room is 5 by 3 by 3 meters.")
        self.assertEqual(spoken(["It is 2026."]), "It is 2026.")
        self.assertIn("50450", spoken(["12 Jalan Ampang, 50450 Kuala Lumpur"]))


if __name__ == "__main__":
    unittest.main()
