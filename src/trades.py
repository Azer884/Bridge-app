"""One business, several trades. A business config may list "extra_trades" (for example ["aircon"]); each is read from
config/trades/<trade>.json and laid over the main config for the conversations that are about that trade.

Which trade a customer means is decided from what they say: fixed words first, the model for messages the words cannot
settle (see intent.read_trade), and a question to the customer when it is still unclear. Nothing is guessed."""
import json
import re
from pathlib import Path

from .prompt import trade_of

ROOT = Path(__file__).resolve().parent.parent
TRADE_DIR = ROOT / "config" / "trades"

# Words of one trade that are also words of another ("wall-mounted" aircon, "ceiling cassette") are taken out first.
_SHARED = re.compile(r"\b(wall[- ]mounted|wall[- ]type|ceiling[- ]cassette|ceiling[- ]mounted|ceiling[- ]concealed)\b", re.I)
_AIRCON = re.compile(
    r"\b(air[- ]?con\w*|air[- ]?cond\w*|a/c|ac units?|ac servic\w*|chemical (?:wash|overhaul)|gas top[- ]?up|"
    r"penghawa dingin|aircond\w*|not cold|tak sejuk|tidak sejuk|air menitis|cuci kimia|tambah gas)\b", re.I)
_PAINT = re.compile(
    r"\b(paint\w*|repaint\w*|walls?|ceilings?|mengecat\w*|\bcat\b|dinding|siling|colou?rs?|warna|plaster)\b", re.I)

NAMES = {"painting": "painting", "aircon": "aircon servicing"}


def detect(message):
    """"painting", "aircon", "both" or None, from the customer's words."""
    text = _SHARED.sub(" ", message or "")
    aircon, paint = bool(_AIRCON.search(text)), bool(_PAINT.search(text))
    if aircon and paint:
        return "both"
    return "aircon" if aircon else "painting" if paint else None


def load(config):
    """{trade: config} for the main trade and every extra trade the config lists. A trade whose file is missing is left out."""
    main = trade_of(config)
    out = {main: config}
    for name in config.get("extra_trades") or []:
        path = TRADE_DIR / f"{name}.json"
        if name == main or not path.is_file():
            continue
        extra = json.loads(path.read_text(encoding="utf-8"))
        merged = {**config, **extra, "trade_type": name}
        merged["privacy"] = config.get("privacy", extra.get("privacy"))      # one privacy promise for the whole business
        merged.pop("extra_trades", None)
        out[name] = merged
    return out


def label(trades):
    """"painting or aircon servicing" for a question to the customer."""
    return " or ".join(NAMES.get(t, t) for t in trades)
