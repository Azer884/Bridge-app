"""Per-customer conversation state and a simple JSON file store."""
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .i18n import SURFACE_WORDS
from .schema import FIELD_ORDER, single_wall

SURFACE_TOKENS = {"wall", "walls", "ceiling", "ceilings", "trim", "door", "doors", "window", "windows",
                  "skirting", "frame", "frames", "architrave", "cornice", "beam", "beams", "dinding", "siling",
                  "pintu", "tingkap"}


@dataclass
class ConversationState:
    conversation_id: str
    verified: dict = field(default_factory=dict)
    history: list = field(default_factory=list)  # [{"role": "user"|"assistant", "content": str}]
    status: str = "collecting_information"
    needs_human: bool = False
    pending_conflict: dict = None  # {"key", "old", "new"} awaiting the customer's choice
    channel: dict = field(default_factory=dict)  # trusted-by-channel {"name", "phone"} (WhatsApp)
    stage: str = "job"             # job -> contact -> wrapup -> done (wrapup only with a persona)
    greeted: bool = False          # the persona's greeting has been sent
    service_checked: bool = False  # the customer asked for a service we offer
    contact_confirmed: bool = False  # name and phone confirmed once; not asked again after a correction
    contact_step: str = ""         # confirm | ask_name | ask_phone
    strikes: int = 0               # blocked or abusive messages
    photo_assessment: dict = None  # combined vision result of the customer's photos
    quote: dict = None             # draft quotation with breakdown (Quotation.to_dict()), SME-only
    quote_status: str = ""         # "" | pending_approval | approved | needs_inspection
    estimated: list = field(default_factory=list)  # measurements the customer only estimated ("maybe 4 to 5 m")
    lang: str = "en"               # en | ms: the language the customer writes in or asked for
    last_field: str = ""           # the measurement answered last, so "nvm its 4m" knows what to fix
    orders: list = field(default_factory=list)      # earlier jobs of the same customer (archived)
    followups: list = field(default_factory=list)   # messages sent while waiting for the SME, for the SME
    waiting_count: int = 0         # replies sent while waiting for the SME's confirmation
    attention: bool = False        # an important follow-up the SME should look at
    created_at: float = 0.0        # when the current job started
    quote_stale: bool = False      # a size changed after pricing: the draft must be recalculated

    def required_fields(self, config):
        wanted = set(config["required_fields"])
        if single_wall(self.verified.get("surfaces")):
            wanted.discard("room_width_m")      # one wall: length x height is enough
        return [k for k in FIELD_ORDER if k in wanted]

    def missing_required(self, config, extra=None):
        have = {**self.verified, **(extra or {})}
        return [k for k in self.required_fields(config) if k not in have]

    def next_missing(self, config):
        missing = self.missing_required(config)
        return missing[0] if missing else None

    def merge(self, accepted):
        for key, value in accepted.items():
            if key == "surfaces":
                items = value if isinstance(value, list) else [value]
                items = [SURFACE_WORDS.get(str(v).lower().strip(), v) for v in items]
                # "bedroom" is a room, not a surface: only walls, ceilings, trim and the like count
                value = [v for v in items if SURFACE_TOKENS & set(re.findall(r"[a-z]+", str(v).lower()))]
                if not value:
                    continue
            if isinstance(value, list):
                old = self.verified.get(key, [])
                self.verified[key] = old + [v for v in value if v not in old]
            else:
                self.verified[key] = value

    def add_turn(self, user_text, reply, status="collecting_information", extracted=None):
        self.history += [{"role": "user", "content": user_text},
                         {"role": "assistant", "content": reply, "status": status,
                          "extracted": extracted or {}}]

    def history_window(self, turns=6):
        """Assistant turns are rendered in the JSON contract so the model keeps answering in it."""
        out = []
        for turn in self.history[-2 * turns:]:
            if turn["role"] == "assistant":
                content = json.dumps({
                    "reply": turn["content"], "extracted_fields": turn.get("extracted", {}),
                    "missing_fields": [], "status": turn.get("status", "collecting_information")})
                out.append({"role": "assistant", "content": content})
            else:
                out.append({"role": turn["role"], "content": turn["content"]})
        return out


class ConversationStore:
    def __init__(self, directory="data/conversations"):
        self.dir = Path(directory)

    def _path(self, conversation_id):
        safe = "".join(c for c in conversation_id if c.isalnum() or c in "-_")
        return self.dir / f"{safe}.json"

    def load(self, conversation_id):
        path = self._path(conversation_id)
        if path.exists():
            return ConversationState(**json.loads(path.read_text(encoding="utf-8")))
        return ConversationState(conversation_id=conversation_id)

    def save(self, state):
        self.dir.mkdir(parents=True, exist_ok=True)
        self._path(state.conversation_id).write_text(
            json.dumps(asdict(state), indent=2), encoding="utf-8")
