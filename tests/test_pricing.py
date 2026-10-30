import json
import unittest
from decimal import Decimal
from pathlib import Path

from src.assessment import ConditionAssessment, classify_text, combine, from_vision_output
from src.pricing import PricingError, compute_quotation

PRICING = json.loads((Path(__file__).resolve().parent / "fixtures" / "pricing_test_rates.json").read_text())["pricing"]


def job(**overrides):
    base = {"room_length_m": 4.0, "room_width_m": 3.0, "room_height_m": 2.5,
            "surfaces": ["walls", "ceiling"], "surface_condition": "no damage"}
    base.update(overrides)
    return base


def total(quote):
    return quote.total


class PricingTests(unittest.TestCase):
    def test_base_room_hand_calculated(self):
        # walls 2*(4+3)*2.5=35, ceiling 12 -> 47 m2, 2 coats
        # paint ceil(94/10)=10 L * 14 = 140; labour 70*3 + 24*3.5 = 294; markup 15% of 434
        q = compute_quotation(job(), PRICING)
        self.assertEqual(q.inputs["wall_area_m2"], 35.0)
        self.assertEqual(q.inputs["ceiling_area_m2"], 12.0)
        self.assertEqual(q.subtotal, Decimal("434.00"))
        self.assertEqual(q.markup, Decimal("65.10"))
        self.assertEqual(q.total, Decimal("499.10"))
        self.assertEqual(q.status, "draft_ready")

    def test_premium_paint_changes_litres_and_price(self):
        # ceil(94/12)=8 L * 22 = 176; labour 294; subtotal 470; markup 70.50
        q = compute_quotation(job(paint_tier="premium please"), PRICING)
        self.assertEqual(q.total, Decimal("540.50"))
        self.assertNotIn("paint tier not specified", " ".join(q.assumptions))

    def test_unspecified_paint_tier_is_a_flagged_assumption(self):
        q = compute_quotation(job(), PRICING)
        self.assertIn("standard", " ".join(q.assumptions))

    def test_moderate_condition_adds_labour_multiplier_and_prep(self):
        # walls 3.75*70=262.50; ceiling 4.38*24=105.12; paint 140; prep 3.525h*30=105.75
        q = compute_quotation(job(surface_condition="paint is peeling and cracked"), PRICING)
        self.assertEqual(q.inputs["condition_level"], "moderate")
        self.assertEqual(q.subtotal, Decimal("613.37"))
        self.assertEqual(q.total, Decimal("705.38"))
        self.assertEqual(q.status, "draft_ready")

    def test_severe_condition_needs_inspection(self):
        q = compute_quotation(job(surface_condition="there is a damp leak"), PRICING)
        self.assertEqual(q.status, "needs_inspection")
        self.assertTrue(any("inspection" in f for f in q.flags))

    def test_vision_mould_forces_inspection_even_if_customer_says_fine(self):
        vision = from_vision_output({"condition_level": "moderate", "issues": ["mould"], "confidence": 0.9})
        q = compute_quotation(job(surface_condition="looks fine"), PRICING, vision)
        self.assertEqual(q.status, "needs_inspection")
        self.assertEqual(q.inputs["condition_level"], "moderate")   # worst of both

    def test_height_surcharge(self):
        # walls only 2*7*3.5=49 m2; unit 3.6; qty 98 -> 352.80; paint 10 L = 140; markup 73.92
        q = compute_quotation(job(room_height_m=3.5, surfaces=["walls"]), PRICING)
        self.assertEqual(q.total, Decimal("566.72"))

    def test_minimum_charge(self):
        q = compute_quotation(job(room_length_m=1.0, room_width_m=1.0, surfaces=["walls"]), PRICING)
        self.assertTrue(q.minimum_charge_applied)
        self.assertEqual(q.total, Decimal("150.00"))

    def test_complexity_flags_and_extra_coat(self):
        vision = from_vision_output({"condition_level": "good", "complexity_flags":
                                     ["intricate_trim", "dark_to_light"], "confidence": 0.9})
        q = compute_quotation(job(), PRICING, vision)
        self.assertEqual(q.inputs["coats"], 3)
        self.assertAlmostEqual(q.inputs["labour_multiplier"], 1.1)

    def test_low_confidence_photo_is_flagged(self):
        vision = from_vision_output({"condition_level": "good", "confidence": 0.3})
        q = compute_quotation(job(), PRICING, vision)
        self.assertEqual(q.status, "needs_inspection")

    def test_unsupported_surface_and_large_area_flagged(self):
        q = compute_quotation(job(surfaces=["walls", "doors"]), PRICING)
        self.assertTrue(any("doors" in f for f in q.flags))
        q = compute_quotation(job(room_length_m=20.0, room_width_m=10.0, room_height_m=3.0), PRICING)
        self.assertTrue(any("exceeds" in f for f in q.flags))

    def test_missing_measurements_raise(self):
        with self.assertRaises(PricingError):
            compute_quotation({"room_length_m": 4.0}, PRICING)

    def test_always_a_draft_for_sme_review(self):
        self.assertTrue(compute_quotation(job(), PRICING).requires_sme_review)

    def test_serialises_to_json(self):
        json.dumps(compute_quotation(job(), PRICING).to_dict())


class AssessmentTests(unittest.TestCase):
    def test_text_classification(self):
        for text, level in [("no damage at all", "good"), ("a few scuffs", "minor"),
                            ("peeling near the window", "moderate"), ("water damage and mould", "severe")]:
            self.assertEqual(classify_text(text).level, level, text)
        self.assertIsNone(classify_text("white walls"))
        self.assertIsNone(classify_text(""))

    def test_vision_output_is_validated(self):
        a = from_vision_output({"condition_level": "minor", "issues": ["cracks", "ghosts"],
                                "complexity_flags": ["stairwell", "pool"], "confidence": 2,
                                "room_length_m": 99, "price": 5})
        self.assertEqual((a.level, a.issues, a.complexity_flags, a.confidence),
                         ("minor", ("cracks",), ("stairwell",), 1.0))
        self.assertFalse(hasattr(a, "room_length_m"))
        self.assertIsNone(from_vision_output({"condition_level": "awful"}))
        self.assertIsNone(from_vision_output("not a dict"))

    def test_combine_takes_worst_level_and_lowest_confidence(self):
        a = ConditionAssessment("minor", ("stains",), (), 0.9, "customer_text")
        b = ConditionAssessment("moderate", ("cracks",), ("stairwell",), 0.7, "vision")
        c = combine(a, None, b)
        self.assertEqual((c.level, c.issues, c.confidence), ("moderate", ("cracks", "stains"), 0.7))
        self.assertIsNone(combine(None, None))


DEMO = json.loads((Path(__file__).resolve().parent.parent / "config" / "business_config.example.json").read_text())["pricing"]


SQFT = Decimal("10.763910416709722")


class MalaysianMarketRateTests(unittest.TestCase):
    """The example rate card is the real 2026 market data in config/painting_prices_malaysia_2026.csv."""

    def quote(self, level="minor", **kw):
        return compute_quotation(job(**kw), DEMO, overrides={"condition_level": level})

    def test_breakdown_sums_to_total_and_is_in_ringgit(self):
        q = self.quote()
        self.assertEqual(q.currency, "MYR")
        self.assertEqual(sum(q.breakdown.values(), Decimal(0)), q.total)

    def test_hand_calculated_walls_and_ceiling_at_market_rates(self):
        # walls 35 m2 and ceiling 12 m2, minor condition: walls RM1.30/sq ft paint+labour and RM0.65/sq ft preparation
        # (SRC001, together the RM1.95 median); ceiling RM1.20/sq ft all-in (SRC003)
        q = self.quote()
        walls, ceiling = Decimal(35) * SQFT, Decimal(12) * SQFT
        expected = (walls * Decimal("1.30")).quantize(Decimal("0.01")) + (walls * Decimal("0.65")).quantize(Decimal("0.01"))             + (ceiling * Decimal("1.20")).quantize(Decimal("0.01"))
        self.assertEqual(q.total, expected)
        self.assertEqual(q.markup, Decimal("0.00"))        # market rates already include the contractor's margin

    def test_the_study_job_lands_on_the_published_median(self):
        # SRC001: 1,205 sq ft of previously painted wall, minor filling and sanding, two coats: median RM1.95/sq ft
        q = compute_quotation(job(room_length_m=10.0, room_width_m=9.99, room_height_m=2.8, surfaces=["walls"]),
                              DEMO, overrides={"condition_level": "minor"})
        sqft = Decimal(str(q.inputs["wall_area_m2"])) * SQFT
        self.assertAlmostEqual(float(q.total / sqft), 1.95, places=2)
        low, high = q.inputs["market_range"]["low"], q.inputs["market_range"]["high"]
        self.assertAlmostEqual(low / float(sqft), 1.70, places=2)       # the study's cheapest quote
        self.assertAlmostEqual(high / float(sqft), 2.30, places=2)      # and its dearest

    def test_good_condition_needs_no_filling(self):
        good, minor = self.quote("good"), self.quote("minor")
        self.assertLess(good.total, minor.total)
        walls_only = compute_quotation(job(surfaces=["walls"]), DEMO, overrides={"condition_level": "good"})
        self.assertAlmostEqual(float(walls_only.total / (Decimal(35) * SQFT)), 1.30, places=2)    # the paint+labour component

    def test_the_same_input_gives_the_same_price(self):
        self.assertEqual(self.quote().to_dict(), self.quote().to_dict())

    def test_outside_klang_valley_is_flagged_for_the_owner(self):
        q = self.quote(address="12 Jalan Setia, Johor Bahru, Johor")
        self.assertIn("no verified 2026 rate", " ".join(q.assumptions))
        self.assertNotIn("no verified 2026 rate", " ".join(self.quote(address="12 Jalan Ampang, Kuala Lumpur").assumptions))

    def test_assumptions_that_are_not_in_the_data_are_labelled(self):
        text = " ".join(self.quote("moderate", paint_tier="premium").assumptions)
        self.assertIn("not in the market data", text)
        self.assertIn("assumption", text)

    def test_minimum_charge_shows_as_its_own_breakdown_line(self):
        q = compute_quotation(job(room_length_m=1.0, room_width_m=1.0, room_height_m=2.0, surfaces=["walls"]), DEMO)
        self.assertTrue(q.minimum_charge_applied)
        self.assertEqual(sum(q.breakdown.values(), Decimal(0)), q.total)
        self.assertIn("Minimum charge top-up", q.breakdown)


if __name__ == "__main__":
    unittest.main()
