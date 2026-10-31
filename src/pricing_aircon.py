"""Deterministic pricing engine for Air Conditioning Servicing SMEs in Malaysia.

Handles unit count, horsepower tiers (1.0HP - 3.0HP), service levels
(General Service, Chemical Wash, Chemical Overhaul), refrigerant gas refills,
and multi-unit volume discounts.
"""
import math
import re
from decimal import Decimal

from .assessment import classify_text, combine, LOW_CONFIDENCE
from .pricing import LineItem, Quotation, PricingError, _d, _money, CENT

LABOUR = "Labour"
MATERIALS = "Gas & Materials"
DISCOUNT = "Multi-unit discount"
OVERHEAD = "Overheads & profit"
MINIMUM = "Minimum charge top-up"

REQUIRED_AIRCON = ["unit_count", "service_type"]


def _extract_units(value):
    """Extract integer unit count from numbers or phrases ('3 units', 'dua biji')."""
    if isinstance(value, (int, float)):
        return max(1, int(value))
    text = str(value or "").lower().strip()
    match = re.search(r"\b(\d+)\b", text)
    if match:
        return max(1, int(match.group(1)))
    word_map = {"one": 1, "satu": 1, "two": 2, "dua": 2, "three": 3, "tiga": 3,
                "four": 4, "empat": 4, "five": 5, "lima": 5}
    for word, count in word_map.items():
        if word in text:
            return count
    return 1


def _match_service_type(text, service_types, default="chemical_wash"):
    t = str(text or "").lower()
    if "overhaul" in t:
        return "chemical_overhaul"
    if "chemical" in t or "kimia" in t:
        return "chemical_wash"
    if "general" in t or "normal" in t or "biasa" in t or "cuci" in t:
        return "general_service"
    for st in service_types:
        if st in t:
            return st
    return default


def _match_horsepower(text, horsepower_tiers, default="1.0hp"):
    t = str(text or "").lower()
    for hp in sorted(horsepower_tiers.keys(), reverse=True):
        clean_hp = hp.replace("hp", "").strip()
        if f"{clean_hp}hp" in t or f"{clean_hp} hp" in t or f"{clean_hp} kuasa" in t:
            return hp
    return default


def compute_aircon_quotation(verified, pricing, vision=None, overrides=None):
    """Compute deterministic aircon servicing estimate from verified fields and rate card."""
    overrides = overrides or {}
    flags, assumptions = [], []

    # 1. Unit count
    raw_units = overrides.get("unit_count") or verified.get("unit_count")
    if not raw_units:
        # Fallback if customer only mentioned service without unit count
        units = 1
        assumptions.append("unit count not specified; priced as 1 unit")
    else:
        units = _extract_units(raw_units)

    # 2. Service type
    service_types = pricing.get("service_types", {})
    raw_service = overrides.get("service_type") or verified.get("service_type", "")
    service_key = _match_service_type(raw_service, service_types, pricing.get("default_service_type", "chemical_wash"))
    service_info = service_types.get(service_key, {
        "label": "Chemical Wash",
        "base_rate": 130.0,
        "hours_per_unit": 1.0,
        "category": LABOUR
    })

    # 3. Horsepower
    hp_tiers = pricing.get("horsepower_multipliers", {"1.0hp": 1.0, "1.5hp": 1.0, "2.0hp": 1.25})
    raw_hp = overrides.get("horsepower") or verified.get("horsepower", "")
    hp_key = _match_horsepower(raw_hp, hp_tiers, pricing.get("default_horsepower", "1.0hp"))
    hp_multiplier = _d(hp_tiers.get(hp_key, 1.0))

    # 4. Condition assessment (checks for severe issues like burnt compressor or electrical tripping)
    text_assessment = classify_text(verified.get("surface_condition") or str(verified.get("brand_or_issue", "")))
    assessment = combine(text_assessment, vision)
    level = "minor"
    issues = ()
    if assessment:
        level, issues = assessment.level, assessment.issues
        if assessment.confidence < LOW_CONFIDENCE:
            flags.append(f"visual inspection has low confidence ({assessment.confidence:.2f})")
    
    if overrides.get("condition_level"):
        level = overrides["condition_level"]

    cond_multipliers = pricing.get("condition_levels", {})
    cond_info = cond_multipliers.get(level, {"multiplier": 1.0})
    cond_multiplier = _d(cond_info.get("multiplier", 1.0))

    # 5. Base Labour Calculation
    base_rate = _d(service_info["base_rate"])
    unit_labour = _money(base_rate * hp_multiplier * cond_multiplier)
    total_labour = _money(unit_labour * Decimal(units))

    lines = []
    lines.append(LineItem(
        description=f"{service_info['label']} ({units}x {hp_key.upper()} unit{'s' if units > 1 else ''})",
        quantity=Decimal(units),
        unit="unit",
        unit_price=unit_labour,
        amount=total_labour,
        category=LABOUR
    ))

    # 6. Gas Refill (if requested)
    gas_requested = False
    req_text = (str(verified.get("service_type", "")) + " " +
                str(verified.get("brand_or_issue", "")) + " " +
                str(verified.get("surface_condition", ""))).lower()
    if "gas" in req_text or "freon" in req_text or overrides.get("gas_topup"):
        gas_requested = True
        gas_cfg = pricing.get("gas_topup", {})
        gas_rate = _d(gas_cfg.get("r32", 80.0))
        gas_amount = _money(gas_rate * Decimal(units))
        lines.append(LineItem(
            description=f"Refrigerant Gas Top-up / Pressure Refill ({units} unit{'s' if units > 1 else ''})",
            quantity=Decimal(units),
            unit="unit",
            unit_price=gas_rate,
            amount=gas_amount,
            category=MATERIALS
        ))

    # 7. Multi-Unit Discount
    discounts = pricing.get("discounts", {})
    tier2_min = discounts.get("multi_unit_tier_2_min", 4)
    tier2_pct = _d(discounts.get("multi_unit_tier_2_pct", 15))
    tier1_min = discounts.get("multi_unit_tier_1_min", 2)
    tier1_pct = _d(discounts.get("multi_unit_tier_1_pct", 10))

    discount_amount = Decimal("0.00")
    if units >= tier2_min and tier2_pct:
        discount_amount = _money(total_labour * tier2_pct / 100)
        lines.append(LineItem(
            description=f"Multi-unit package discount ({tier2_pct}% off labour for {units} units)",
            quantity=Decimal(1),
            unit="discount",
            unit_price=-discount_amount,
            amount=-discount_amount,
            category=DISCOUNT
        ))
    elif units >= tier1_min and tier1_pct:
        discount_amount = _money(total_labour * tier1_pct / 100)
        lines.append(LineItem(
            description=f"Multi-unit package discount ({tier1_pct}% off labour for {units} units)",
            quantity=Decimal(1),
            unit="discount",
            unit_price=-discount_amount,
            amount=-discount_amount,
            category=DISCOUNT
        ))

    # 8. Totals & Markup
    subtotal = _money(sum((l.amount for l in lines), Decimal("0.00")))
    markup_pct = _d(pricing.get("markup_pct", 0))
    markup = _money(subtotal * markup_pct / 100) if markup_pct else Decimal("0.00")
    total = subtotal + markup

    # Minimum charge
    minimum = _d(pricing.get("minimum_job_charge", 80.0))
    minimum_applied = total < minimum
    if minimum_applied:
        top_up = minimum - total
        lines.append(LineItem(
            description="Minimum callout top-up",
            quantity=Decimal(1),
            unit="charge",
            unit_price=top_up,
            amount=top_up,
            category=MINIMUM
        ))
        total = minimum

    # 9. Breakdown
    breakdown = {}
    for line in lines:
        breakdown[line.category] = breakdown.get(line.category, Decimal("0.00")) + line.amount
    if markup:
        breakdown[OVERHEAD] = markup

    # 10. Scheduling calculation
    hours_per_unit = _d(service_info.get("hours_per_unit", 1.0))
    gas_hours = _d(pricing.get("gas_topup", {}).get("hours", 0.3)) if gas_requested else Decimal("0.0")
    total_hours = float((hours_per_unit * Decimal(units) + gas_hours).quantize(Decimal("0.1")))
    crew = max(1, int(pricing.get("crew_size", 2)))
    workday = _d(pricing.get("workday_hours", 8))
    hours_on_site = float(round(total_hours / crew, 1))
    days = max(1, math.ceil(total_hours / crew / float(workday)))

    schedule = {
        "service_hours": total_hours,
        "total_labour_hours": total_hours,
        "crew_size": crew,
        "hours_on_site": hours_on_site,
        "working_days": days
    }

    # 11. Inspection triggers
    if level in pricing.get("inspection_levels", ["severe"]):
        flags.append(f"unit condition '{level}' indicates possible compressor/PCB breakdown requiring on-site diagnostic")
    if "trip" in req_text or "bocor" in req_text:
        flags.append("electrical tripping or concealed piping leak reported: verify before confirming")

    return Quotation(
        status="needs_inspection" if flags else "draft_ready",
        currency=pricing.get("currency", "MYR"),
        lines=lines,
        subtotal=subtotal,
        markup=markup,
        total=_money(total),
        minimum_charge_applied=minimum_applied,
        flags=flags,
        assumptions=assumptions,
        breakdown=breakdown,
        schedule=schedule,
        inputs={
            "unit_count": units,
            "service_type": service_key,
            "horsepower": hp_key,
            "gas_requested": gas_requested,
            "condition_level": level
        }
    )
