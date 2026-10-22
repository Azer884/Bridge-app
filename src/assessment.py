"""Surface condition and job complexity, from the customer's words or a vision model.

An assessment never carries a price or a dimension. It only selects a configured level and
configured flags; the pricing engine turns those into money.
"""
import re
from dataclasses import dataclass

LEVELS = ["good", "minor", "moderate", "severe"]
ISSUES = {"peeling", "flaking", "cracks", "stains", "bubbling", "holes", "damp", "mould",
          "water_damage"}
COMPLEXITY_FLAGS = {"intricate_trim", "stairwell", "furniture_clutter", "dark_to_light"}
LOW_CONFIDENCE = 0.6


@dataclass(frozen=True)
class ConditionAssessment:
    level: str
    issues: tuple = ()
    complexity_flags: tuple = ()
    confidence: float = 1.0
    source: str = "customer_text"


_TEXT_RULES = [  # checked in order; first hit wins
    ("severe", r"\b(damp|leak\w*|water damage\w*|mou?ld|structural|rot(ten)?)\b"),
    ("good", r"\b(good condition|no (damage|cracks|issues|problems|marks)|perfect|fine|clean|new)\b"),
    ("moderate", r"\b(peeling|flaking|bubbling|cracks?|cracked|holes?|stains?|stained)\b"),
    ("minor", r"\b(hairline|scuffs?|marks?|dirty|faded|worn|minor|small|dents?)\b"),
]
_TEXT_ISSUES = {
    "peeling": "peeling", "flaking": "flaking", "bubbling": "bubbling", "crack": "cracks",
    "hole": "holes", "stain": "stains", "damp": "damp", "mould": "mould", "mold": "mould",
    "leak": "water_damage", "water damage": "water_damage",
}


def classify_text(text):
    """Deterministic read of the customer's own description. None when nothing is said."""
    if not isinstance(text, str) or not text.strip():
        return None
    lowered = text.lower()
    level = next((lvl for lvl, pat in _TEXT_RULES if re.search(pat, lowered)), None)
    if level is None:
        return None
    issues = tuple(sorted({v for k, v in _TEXT_ISSUES.items() if k in lowered}))
    return ConditionAssessment(level, issues, (), 1.0, "customer_text")


def from_vision_output(raw):
    """Validate a vision model's JSON. Unknown values are dropped; anything else (including
    any dimension it volunteers) is ignored. Returns None if the level is unusable."""
    if not isinstance(raw, dict) or raw.get("condition_level") not in LEVELS:
        return None
    issues = tuple(sorted({i for i in raw.get("issues", []) if i in ISSUES}))
    flags = tuple(sorted({f for f in raw.get("complexity_flags", []) if f in COMPLEXITY_FLAGS}))
    try:
        confidence = min(1.0, max(0.0, float(raw.get("confidence", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0
    return ConditionAssessment(raw["condition_level"], issues, flags, confidence, "vision")


def combine(*assessments):
    """Conservative merge: worst level, all issues and flags, lowest confidence."""
    found = [a for a in assessments if a is not None]
    if not found:
        return None
    worst = max(found, key=lambda a: LEVELS.index(a.level))
    return ConditionAssessment(
        worst.level,
        tuple(sorted({i for a in found for i in a.issues})),
        tuple(sorted({f for a in found for f in a.complexity_flags})),
        min(a.confidence for a in found),
        "+".join(sorted({a.source for a in found})))
