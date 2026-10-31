"""Output contract and field catalogue shared by prompt, validation and state."""
from dataclasses import dataclass, field
from enum import Enum

from .i18n import t


class Status(str, Enum):
    COLLECTING = "collecting_information"
    CLARIFICATION = "needs_clarification"
    READY = "ready_for_estimate"
    HUMAN = "needs_human"


STATUS_VALUES = [s.value for s in Status]


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    kind: str  # text | phone | email | measurement | list
    hint: str = ""
    ask: str = ""  # backend template question, used when the model cannot follow the one-question rule


# Order here is the order questions are asked in. The address comes last, just before the contact step.
FIELD_CATALOGUE = [
    FieldSpec("customer_name", "Customer name", "text", ask="What name should we put the quotation under?"),
    FieldSpec("phone", "Phone number", "phone", ask="What is the best phone number to reach you on?"),
    FieldSpec("email", "Email address", "email", ask="What is your email address?"),
    FieldSpec("property_type", "Property type", "text", ask="What type of property is it?"),
    FieldSpec("surfaces", "Surfaces to paint", "list", "e.g. walls, ceiling", ask="Which surfaces would you like painted?"),
    FieldSpec("room_length_m", "Room length", "measurement", "quote the customer's own words, e.g. \"4 metres\"", ask="How long is the room?"),
    FieldSpec("room_width_m", "Room width", "measurement", "quote the customer's own words", ask="How wide is the room?"),
    FieldSpec("room_height_m", "Room height", "measurement", "quote the customer's own words", ask="How tall is the room?"),
    FieldSpec("paint_tier", "Paint type or tier", "text", ask="What paint quality would you like: economy, standard or premium?"),
    FieldSpec("colour", "Paint colour", "text", ask="What colour would you like?"),
    FieldSpec("service_type", "Aircon service wanted", "text", "general service, chemical wash, chemical overhaul or gas top-up", ask="Which aircon service do you need?"),
    FieldSpec("unit_count", "Number of aircon units", "text", "e.g. \"2 units\"", ask="How many aircon units need servicing?"),
    FieldSpec("horsepower", "Aircon horsepower", "text", "e.g. \"1.5 HP\", or \"not sure\"", ask="What horsepower are the units?"),
    FieldSpec("aircon_issue", "What the customer notices with the aircon", "text", "e.g. not cold, water dripping, a smell, or \"no problem\"", ask="Is anything wrong with the aircon?"),
    FieldSpec("preferred_datetime", "Preferred appointment date and time", "text", ask="What date and time would you prefer for the appointment?"),
    FieldSpec("surface_condition", "Surface condition or damage", "text", ask="What condition are the surfaces in?"),
    FieldSpec("address", "Property address", "text", ask="What is the address of the property?"),
]
FIELDS = {f.key: f for f in FIELD_CATALOGUE}


def ask_for(key, state):
    """The backend's template question for a field, in the customer's language and worded for one wall
    when that is the job. A returning customer is asked whether the address is the same."""
    lang = getattr(state, "lang", "en")
    if key == "address" and getattr(state, "orders", None):
        previous = state.orders[-1]["verified"].get("address")
        if previous:
            return t("ask_address_again", lang, address=previous)
    if single_wall(state.verified.get("surfaces")):
        if key == "room_length_m":
            return t("ask_wall_length_m", lang)
        if key == "room_height_m":
            return t("ask_wall_height_m", lang)
    if key == "preferred_datetime" and getattr(state, "date_issue", ""):
        issue, state.date_issue = state.date_issue, ""         # the date they gave has gone by: say so, then ask again
        return t(issue, lang)
    return t(f"ask_{key}", lang)


def single_wall(surfaces):
    """True when the customer wants one wall painted (and no ceiling): its area is length x height,
    so the room width is not needed."""
    items = [str(s).lower() for s in (surfaces or [])]
    walls = [s for s in items if "wall" in s]
    return bool(walls) and all("walls" not in s and "all" not in s.split() for s in walls) \
        and not any("ceil" in s for s in items)
FIELD_ORDER = [f.key for f in FIELD_CATALOGUE]


@dataclass
class ModelResponse:
    reply: str
    extracted_fields: dict = field(default_factory=dict)
    missing_fields: list = field(default_factory=list)
    status: str = Status.COLLECTING.value
