"""Deterministic quotation engine. No model is involved: every number comes from the
customer's verified measurements and the business's configured rate card."""
import math
import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from .assessment import LEVELS, LOW_CONFIDENCE, classify_text, combine
from .rooms import all_rooms
from .schema import single_wall

CENT = Decimal("0.01")
INSPECTION_ISSUES = {"damp", "mould", "water_damage"}
REQUIRED = ["room_length_m", "room_width_m", "room_height_m", "surfaces"]
LABOUR, PAINT, PREP = "Labour", "Paint", "Surface preparation"
MATERIALS, OVERHEAD, MINIMUM = "Materials & sundries", "Overheads & profit", "Minimum charge top-up"


class PricingError(ValueError):
    pass


def _d(value):
    return Decimal(str(value))


def _money(value):
    return value.quantize(CENT, ROUND_HALF_UP)


@dataclass
class LineItem:
    description: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    amount: Decimal
    category: str = ""

    def to_dict(self):
        return {"description": self.description, "quantity": float(self.quantity), "unit": self.unit,
                "unit_price": float(self.unit_price), "amount": float(self.amount),
                "category": self.category}


@dataclass
class Quotation:
    status: str                      # draft_ready | needs_inspection
    currency: str
    lines: list
    subtotal: Decimal
    markup: Decimal
    total: Decimal
    minimum_charge_applied: bool
    flags: list = field(default_factory=list)        # reasons a human must look
    assumptions: list = field(default_factory=list)  # defaults the config authorised
    inputs: dict = field(default_factory=dict)
    breakdown: dict = field(default_factory=dict)     # category -> amount, sums to total
    requires_sme_review: bool = True                  # a quotation is always a draft first
    schedule: dict = field(default_factory=dict)      # estimated working hours, crew and days (for booking)

    def to_dict(self):
        return {
            "status": self.status, "currency": self.currency,
            "lines": [line.to_dict() for line in self.lines],
            "breakdown": {k: float(v) for k, v in self.breakdown.items()},
            "subtotal": float(self.subtotal), "markup": float(self.markup), "total": float(self.total),
            "minimum_charge_applied": self.minimum_charge_applied, "flags": self.flags,
            "assumptions": self.assumptions, "inputs": self.inputs,
            "requires_sme_review": self.requires_sme_review, "schedule": self.schedule,
        }


def _schedule(area, coats, multiplier, prep_hours, pricing):
    """Working-hour estimate for the calendar: deterministic, from the same inputs as the price.
    Defaults are demo rates (a painter covers about 9 m2 per hour per coat, cutting in included)."""
    if not area:
        return {}
    rate = _d(pricing.get("painting_m2_per_hour_per_painter", 9))
    painting = area * coats / rate * multiplier
    setup = _d(pricing.get("setup_cleanup_hours", 1))
    hours = painting + prep_hours + setup
    crew = max(1, int(pricing.get("crew_size", 2)))
    day = _d(pricing.get("workday_hours", 8))
    days = max(1, math.ceil(hours / crew / day))
    return {"painting_hours": float(round(painting, 1)), "prep_hours": float(round(prep_hours, 1)),
            "setup_cleanup_hours": float(setup), "total_labour_hours": float(round(hours, 1)),
            "crew_size": crew, "hours_on_site": float(round(hours / crew, 1)), "working_days": days}


def compute_quotation(verified, pricing, vision=None, overrides=None):
    """verified: the conversation's verified fields. pricing: config['pricing'].
    vision: optional validated ConditionAssessment from a photo.
    overrides: the owner's corrections from the dashboard: condition_level, coats, tier."""
    overrides = overrides or {}
    one_wall = single_wall(verified.get("surfaces"))
    missing = [k for k in REQUIRED if k not in verified and not (one_wall and k == "room_width_m")]
    if missing:
        raise PricingError(f"cannot price yet, missing: {missing}")

    flags, assumptions = [], []
    rooms = [(_d(l or 0), _d(w or 0), _d(h or 0)) for _, l, w, h in all_rooms(verified)]
    height = max(h for _, _, h in rooms)             # the tallest room decides the height surcharge

    walls, ceiling = False, False
    for surface in verified["surfaces"]:
        text = str(surface).lower()
        if "wall" in text:
            walls = True
        elif "ceil" in text:
            ceiling = True
        else:
            flags.append(f"unsupported surface '{surface}': needs manual pricing")
    if not walls and not ceiling:
        flags.append("no priceable surface (walls or ceiling) requested")

    if one_wall:
        wall_area = sum((l * h for l, _, h in rooms), Decimal(0))   # one wall each; the width given is not used
        assumptions.append("a single wall is painted: area = length x height")
    else:
        wall_area = sum((2 * (l + w) * h for l, w, h in rooms), Decimal(0)) if walls else Decimal(0)
    ceiling_area = sum((l * w for l, w, _ in rooms), Decimal(0)) if ceiling else Decimal(0)
    if len(rooms) > 1:
        assumptions.append(f"{len(rooms)} rooms are painted; the same surfaces, paint and condition apply to each")
    area = wall_area + ceiling_area
    assumptions.append("openings (doors, windows) are not deducted from the area")

    # condition: the customer's words and the photo, worst of both
    text_assessment = classify_text(verified.get("surface_condition"))
    assessment = combine(text_assessment, vision)
    if assessment is None:
        level = pricing["unknown_condition_level"]
        assumptions.append(f"surface condition not provided; priced as '{level}'")
        issues, complexity = (), ()
    else:
        level, issues, complexity = assessment.level, assessment.issues, assessment.complexity_flags
        if assessment.confidence < LOW_CONFIDENCE:
            flags.append(f"photo assessment has low confidence ({assessment.confidence:.2f})")
    if overrides.get("condition_level") in pricing["condition_levels"]:
        level, issues = overrides["condition_level"], ()
        assumptions.append(f"surface condition set to '{level}' by the owner")
    condition = pricing["condition_levels"][level]

    # paint tier
    tier_text = str(verified.get("paint_tier", "")).lower()
    tier = next((t for t in pricing["paint_tiers"] if re.search(rf"\b{re.escape(t)}\b", tier_text)), None)
    if overrides.get("tier") in pricing["paint_tiers"]:
        tier = overrides["tier"]
    elif tier is None:
        tier = pricing["default_paint_tier"]
        assumptions.append(f"paint tier not specified; priced as '{tier}'")
    paint = pricing["paint_tiers"][tier]

    coats = int(pricing["coats"]) + sum(
        1 for f in complexity if f in pricing.get("extra_coat_flags", []))
    if overrides.get("coats"):
        coats = max(1, min(4, int(overrides["coats"])))

    # labour
    labour_rates = pricing["labour_per_m2_per_coat"]
    multiplier = _d(condition["labour_multiplier"])
    if height > _d(pricing["height_surcharge"]["above_m"]):
        multiplier *= _d(pricing["height_surcharge"]["multiplier"])
    complexity_multiplier = Decimal(1)
    for flag in complexity:
        complexity_multiplier *= _d(pricing["complexity_multipliers"].get(flag, 1))
    multiplier *= min(complexity_multiplier, _d(pricing["max_complexity_multiplier"]))

    lines = []
    for label, surface_area, rate in (("walls", wall_area, labour_rates["walls"]),
                                      ("ceiling", ceiling_area, labour_rates["ceiling"])):
        if surface_area:
            unit_price = _money(_d(rate) * multiplier)
            quantity = surface_area * coats
            lines.append(LineItem(f"Painting labour - {label} ({coats} coats)", quantity,
                                  "m2 coat", unit_price, _money(quantity * unit_price), LABOUR))

    # paint: litres for every coat plus wastage, bought in whole litres
    wastage = 1 + _d(pricing.get("paint_wastage_pct", 0)) / 100
    litres = Decimal(math.ceil(area * coats * wastage / _d(paint["coverage_m2_per_litre"]))) if area else Decimal(0)
    paint_amount = Decimal(0)
    if litres:
        paint_amount = _money(litres * _d(paint["price_per_litre"]))
        lines.append(LineItem(f"Paint - {tier}", litres, "litre", _d(paint["price_per_litre"]),
                              paint_amount, PAINT))

    # surface preparation
    prep_hours = area / 10 * _d(condition["prep_hours_per_10m2"])
    if prep_hours:
        prep_rate = _d(pricing["prep_hourly_rate"])
        lines.append(LineItem(f"Surface preparation ({level} condition)", prep_hours, "hour",
                              prep_rate, _money(prep_hours * prep_rate), PREP))

    # masking tape, drop sheets, sandpaper, filler, brushes and rollers
    sundries_pct = _d(pricing.get("sundries_pct_of_paint", 0))
    if paint_amount and sundries_pct:
        sundries = _money(paint_amount * sundries_pct / 100)
        lines.append(LineItem(f"Masking, drop sheets, sandpaper, filler, rollers ({sundries_pct}% of paint)",
                              Decimal(1), "lot", sundries, sundries, MATERIALS))

    subtotal = _money(sum((line.amount for line in lines), Decimal(0)))
    markup = _money(subtotal * _d(pricing["markup_pct"]) / 100)
    total = subtotal + markup
    minimum = _d(pricing["minimum_job_charge"])
    minimum_applied = bool(area) and total < minimum
    breakdown = {}
    for line in lines:
        breakdown[line.category] = breakdown.get(line.category, Decimal(0)) + line.amount
    breakdown[OVERHEAD] = markup
    if minimum_applied:
        breakdown[MINIMUM] = minimum - total
        total = minimum

    schedule = _schedule(area, coats, multiplier, prep_hours, pricing)

    # anything that needs a person before this can be sent
    if level in pricing["inspection_levels"]:
        flags.append(f"surface condition '{level}' requires an inspection")
    if INSPECTION_ISSUES & set(issues):
        flags.append(f"issues needing inspection: {sorted(INSPECTION_ISSUES & set(issues))}")
    if area > _d(pricing["max_area_without_inspection_m2"]):
        flags.append(f"area {area} m2 exceeds {pricing['max_area_without_inspection_m2']} m2")

    return Quotation(
        status="needs_inspection" if flags else "draft_ready", currency=pricing["currency"],
        lines=lines, subtotal=subtotal, markup=markup, total=_money(total),
        minimum_charge_applied=minimum_applied, flags=flags, assumptions=assumptions,
        breakdown=breakdown, schedule=schedule,
        inputs={"wall_area_m2": float(wall_area), "ceiling_area_m2": float(ceiling_area),
                "rooms": len(rooms), "coats": coats, "paint_tier": tier, "condition_level": level,
                "condition_issues": list(issues), "complexity_flags": list(complexity),
                "labour_multiplier": float(multiplier), "litres": float(litres)})
