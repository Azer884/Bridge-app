"""Output contract and field catalogue shared by prompt, validation and state."""
from dataclasses import dataclass, field
from enum import Enum


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


# Order here is the order questions are asked in.
FIELD_CATALOGUE = [
    FieldSpec("customer_name", "Customer name", "text", ask="What name should we put the quotation under?"),
    FieldSpec("phone", "Phone number", "phone", ask="What is the best phone number to reach you on?"),
    FieldSpec("email", "Email address", "email", ask="What is your email address?"),
    FieldSpec("address", "Property address", "text", ask="What is the address of the property?"),
    FieldSpec("property_type", "Property type", "text", ask="What type of property is it?"),
    FieldSpec("surfaces", "Surfaces to paint", "list", "e.g. walls, ceiling", ask="Which surfaces would you like painted?"),
    FieldSpec("room_length_m", "Room length", "measurement", "quote the customer's own words, e.g. \"4 metres\"", ask="How long is the room?"),
    FieldSpec("room_width_m", "Room width", "measurement", "quote the customer's own words", ask="How wide is the room?"),
    FieldSpec("room_height_m", "Room height", "measurement", "quote the customer's own words", ask="How tall is the room?"),
    FieldSpec("surface_condition", "Surface condition or damage", "text", ask="What condition are the surfaces in?"),
    FieldSpec("paint_tier", "Paint type or tier", "text", ask="What type of paint would you like?"),
    FieldSpec("colour", "Paint colour", "text", ask="What colour would you like?"),
    FieldSpec("preferred_datetime", "Preferred appointment date and time", "text", ask="What date and time would you prefer for the appointment?"),
]
FIELDS = {f.key: f for f in FIELD_CATALOGUE}
FIELD_ORDER = [f.key for f in FIELD_CATALOGUE]


@dataclass
class ModelResponse:
    reply: str
    extracted_fields: dict = field(default_factory=dict)
    missing_fields: list = field(default_factory=list)
    status: str = Status.COLLECTING.value
