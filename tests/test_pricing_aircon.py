import json
import unittest
from decimal import Decimal
from src.pricing import Quotation
from src.pricing_aircon import compute_aircon_quotation

SAMPLE_AIRCON_PRICING = {
    "currency": "MYR",
    "trade_type": "aircon",
    "crew_size": 2,
    "workday_hours": 8,
    "minimum_job_charge": 80.0,
    "markup_pct": 10,
    "service_types": {
        "general_service": {
            "label": "General Service",
            "base_rate": 60.0,
            "hours_per_unit": 0.6,
            "category": "Labour"
        },
        "chemical_wash": {
            "label": "Chemical Wash",
            "base_rate": 130.0,
            "hours_per_unit": 1.0,
            "category": "Labour"
        },
        "chemical_overhaul": {
            "label": "Chemical Overhaul",
            "base_rate": 180.0,
            "hours_per_unit": 1.8,
            "category": "Labour"
        }
    },
    "default_service_type": "chemical_wash",
    "horsepower_multipliers": {
        "1.0hp": 1.0,
        "1.5hp": 1.0,
        "2.0hp": 1.25
    },
    "default_horsepower": "1.0hp",
    "gas_topup": {
        "r32": 80.0,
        "hours": 0.3
    },
    "discounts": {
        "multi_unit_tier_1_min": 2,
        "multi_unit_tier_1_pct": 10,
        "multi_unit_tier_2_min": 4,
        "multi_unit_tier_2_pct": 15
    },
    "condition_levels": {
        "good": {"multiplier": 1.0},
        "minor": {"multiplier": 1.0},
        "severe": {"multiplier": 1.35}
    },
    "inspection_levels": ["severe"]
}


class TestAirconPricing(unittest.TestCase):

    def test_single_unit_chemical_wash(self):
        job = {"unit_count": 1, "service_type": "chemical_wash", "horsepower": "1.0hp"}
        q = compute_aircon_quotation(job, SAMPLE_AIRCON_PRICING)
        self.assertIsInstance(q, Quotation)
        self.assertEqual(q.status, "draft_ready")
        self.assertEqual(q.currency, "MYR")
        # 130 base + 10% markup = 143.00
        self.assertEqual(q.total, Decimal("143.00"))
        self.assertEqual(q.inputs["unit_count"], 1)

    def test_multi_unit_discount(self):
        # 3 units chemical wash -> 10% discount on labour
        job = {"unit_count": 3, "service_type": "chemical_wash", "horsepower": "1.0hp"}
        q = compute_aircon_quotation(job, SAMPLE_AIRCON_PRICING)
        # Labour: 3 * 130 = 390. Discount 10% = -39. Subtotal = 351. Markup 10% = 35.10. Total = 386.10
        self.assertEqual(q.total, Decimal("386.10"))
        # Check discount line exists
        disc_lines = [l for l in q.lines if l.category == "Multi-unit discount"]
        self.assertEqual(len(disc_lines), 1)
        self.assertEqual(disc_lines[0].amount, Decimal("-39.00"))

    def test_horsepower_multiplier(self):
        # 1 unit 2.0HP chemical overhaul
        job = {"unit_count": 1, "service_type": "chemical_overhaul", "horsepower": "2.0hp"}
        q = compute_aircon_quotation(job, SAMPLE_AIRCON_PRICING)
        # Base: 180 * 1.25 = 225. Markup 10% = 22.50. Total = 247.50
        self.assertEqual(q.total, Decimal("247.50"))

    def test_gas_topup_and_json_serialization(self):
        job = {"unit_count": 2, "service_type": "general service with gas topup"}
        q = compute_aircon_quotation(job, SAMPLE_AIRCON_PRICING)
        self.assertTrue(q.inputs["gas_requested"])
        payload = q.to_dict()
        self.assertIn("schedule", payload)
        self.assertIn("lines", payload)
        dumped = json.dumps(payload)
        self.assertTrue(len(dumped) > 50)

    def test_severe_condition_triggers_inspection(self):
        job = {"unit_count": 1, "service_type": "chemical_wash", "surface_condition": "compressor tripping power"}
        q = compute_aircon_quotation(job, SAMPLE_AIRCON_PRICING)
        self.assertEqual(q.status, "needs_inspection")
        self.assertTrue(len(q.flags) > 0)


if __name__ == "__main__":
    unittest.main()
