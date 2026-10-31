"""Surface condition and job complexity, from the customer's words or a vision model.

An assessment never carries a price or a dimension. It only selects a configured level and
configured flags; the pricing engine turns those into money.
"""
import re
from dataclasses import dataclass, field

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
    surface: bool = True            # False: the photo does not show a wall or ceiling (a face, a shirt, food, a car...)
    subject: str = ""               # what the model says the photo shows; only used to cross-check, never shown
    details: dict = field(default_factory=dict)     # trade extras, such as {"unit_type": "wall_mounted"} for an aircon photo


_TEXT_RULES = [  # checked in order; first hit wins
    ("severe", r"\b(damp|leak\w*|water damage\w*|mou?ld|structural|rot(ten)?|lembap|bocor|berkulat|kulat|"
                r"struktur|reput)\b"),
    ("good", r"\b(good condition|no (damage|cracks|issues|problems|marks)|perfect|fine|clean|new|"
             r"keadaan baik|elok|bersih|baru|tiada (kerosakan|retak|masalah))\b"),
    ("moderate", r"\b(peeling|flaking|bubbling|cracks?|cracked|holes?|stains?|stained|mengelupas|retak|"
                 r"berlubang|lubang|kotor teruk|bertompok)\b"),
    ("minor", r"\b(hairline|scuffs?|marks?|dirty|faded|worn|minor|small|dents?|calar|kotor|pudar|haus|"
              r"retak halus)\b"),
]
_TEXT_ISSUES = {
    "mengelupas": "peeling", "retak": "cracks", "lubang": "holes", "lembap": "damp", "kulat": "mould",
    "bocor": "water_damage",
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


# Whatever the model says about is_surface, a subject that is plainly not a paintable surface is not one.
_NOT_A_SURFACE = re.compile(
    r"\b(person|people|man|woman|boy|girl|child|baby|face|selfie|portrait|head|beard|hair|mustache|moustache|hand|"
    r"finger|body|shirt|t-?shirt|clothes|clothing|dress|jacket|shoe|bag|food|meal|drink|fruit|animal|pet|dog|cat|bird|"
    r"car|vehicle|motorcycle|bike|phone|screen|screenshot|laptop|document|paper|receipt|logo|meme|cartoon|toy|plant|"
    r"flower|tree|sky|landscape|sea|beach|furniture|sofa|chair|table|bed)\b", re.I)
_PAINTABLE = re.compile(r"\b(walls?|ceilings?|rooms?|house|building|interior|exterior|stairwell|corridor|hallway|"
                        r"bedroom|kitchen|bathroom|living|facade|fence|plaster|paint(ed)?)\b", re.I)


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
    subject = str(raw.get("subject") or raw.get("what_is_it") or "")[:60]
    flag = raw.get("is_surface", True)
    surface = flag in (True, "true", "True", "yes", 1) and not (_NOT_A_SURFACE.search(subject) and not _PAINTABLE.search(subject))
    if not surface:
        return ConditionAssessment("good", (), (), 0.0, "vision", False, subject)
    return ConditionAssessment(raw["condition_level"], issues, flags, confidence, "vision", True, subject)


AIRCON_ISSUES = {"dirty_filter", "water_stains", "water_leak", "ice_buildup", "mould", "rust", "damaged_casing", "error_light"}
UNIT_TYPES = {"wall_mounted", "ceiling_cassette", "ducted", "floor_standing", "outdoor_condenser"}


def from_aircon_output(raw):
    """Validate a vision model's JSON for a photo of an aircon unit. Only the allowed words are kept, and the model
    supplies no number: no horsepower, no count, no price. Returns None if the level is unusable."""
    if not isinstance(raw, dict) or raw.get("condition_level") not in LEVELS:
        return None
    issues = tuple(sorted({i for i in raw.get("issues", []) if i in AIRCON_ISSUES}))
    try:
        confidence = min(1.0, max(0.0, float(raw.get("confidence", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0
    subject = str(raw.get("what_is_it") or "")[:60]
    if raw.get("is_unit", False) not in (True, "true", "True", "yes", 1):
        return ConditionAssessment("good", (), (), 0.0, "vision", False, subject)
    unit = raw.get("unit_type") if raw.get("unit_type") in UNIT_TYPES else ""
    return ConditionAssessment(raw["condition_level"], issues, (), confidence, "vision", True, subject,
                               {"unit_type": unit} if unit else {})


def from_dict(data):
    """Rebuild an assessment saved in the conversation state (JSON turns tuples into lists)."""
    return ConditionAssessment(data["level"], tuple(data["issues"]), tuple(data["complexity_flags"]),
                               data["confidence"], data["source"], data.get("surface", True), data.get("subject", ""),
                               data.get("details") or {})


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
        "+".join(sorted({a.source for a in found})),
        details={k: v for a in found for k, v in a.details.items()})
