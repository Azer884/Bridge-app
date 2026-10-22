"""Per-customer conversation state and a simple JSON file store."""
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .schema import FIELD_ORDER


@dataclass
class ConversationState:
    conversation_id: str
    verified: dict = field(default_factory=dict)
    history: list = field(default_factory=list)  # [{"role": "user"|"assistant", "content": str}]
    status: str = "collecting_information"
    needs_human: bool = False
    pending_conflict: dict = None  # {"key", "old", "new"} awaiting the customer's choice
    channel: dict = field(default_factory=dict)  # trusted-by-channel {"name", "phone"} (WhatsApp)
    stage: str = "job"             # job -> contact -> done
    contact_step: str = ""         # confirm | ask_name | ask_phone
    strikes: int = 0               # blocked or abusive messages

    def required_fields(self, config):
        wanted = set(config["required_fields"])
        return [k for k in FIELD_ORDER if k in wanted]

    def missing_required(self, config, extra=None):
        have = {**self.verified, **(extra or {})}
        return [k for k in self.required_fields(config) if k not in have]

    def next_missing(self, config):
        missing = self.missing_required(config)
        return missing[0] if missing else None

    def merge(self, accepted):
        for key, value in accepted.items():
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
