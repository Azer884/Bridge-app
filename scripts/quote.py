"""Price a saved conversation: python scripts/quote.py <conversation_id> [--vision=path.json | --image=photo.jpg]

Reads data/conversations/<id>.json and config/business_config.example.json. The optional
vision file holds a vision model's JSON output; it is validated before use.
"""
import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.assessment import from_vision_output  # noqa: E402
from src.conversation import ConversationStore  # noqa: E402
from src.pricing import PricingError, compute_quotation  # noqa: E402
from src.runpod_client import RunPodClient  # noqa: E402
from src.vision import assess_image  # noqa: E402

MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def main():
    flags = {a.split("=", 1)[0]: a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--") and "=" in a}
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    config = json.loads((ROOT / "config" / "business_config.example.json").read_text())
    state = ConversationStore(ROOT / "data" / "conversations").load(args[0])
    vision = None
    if "--vision" in flags:
        vision = from_vision_output(json.loads(Path(flags["--vision"]).read_text()))
        if vision is None:
            sys.exit("vision file did not contain a usable assessment")
    if "--image" in flags:
        path = Path(flags["--image"])
        mime = MIME.get(path.suffix.lower())
        if mime is None:
            sys.exit(f"unsupported image type {path.suffix}")
        client = RunPodClient.from_env("RUNPOD_VISION_ENDPOINT_ID", sampling={"temperature": 0.1, "max_tokens": 300})
        vision, _ = assess_image(client, path.read_bytes(), mime)
        if vision is None:
            sys.exit("vision model returned no usable assessment")
        print(f"PHOTO ASSESSMENT: {vision.level}, issues {list(vision.issues)}, "
              f"flags {list(vision.complexity_flags)}, confidence {vision.confidence}\n")
    try:
        quote = compute_quotation(state.verified, config["pricing"], vision)
    except PricingError as err:
        sys.exit(str(err))

    cur = quote.currency
    area_m2 = quote.inputs["wall_area_m2"] + quote.inputs["ceiling_area_m2"]
    print(f"DRAFT QUOTATION ({quote.status}) - demo estimates, SME review required")
    print(f"Paint area {area_m2:.1f} m2 ({area_m2 * 10.7639:.0f} sq ft), {quote.inputs['coats']} coats, "
          f"{quote.inputs['paint_tier']} paint, surface {quote.inputs['condition_level']}\n")
    for category in dict.fromkeys(line.category for line in quote.lines):
        print(f"  {category}")
        for line in quote.lines:
            if line.category == category:
                print(f"    {line.description:<62} {line.quantity:>8.2f} {line.unit:<8} x {line.unit_price:>7.2f} = {line.amount:>9.2f}")
    print(f"\n  Subtotal {quote.subtotal:.2f} + overheads & profit {quote.markup:.2f}")
    print("\n  BREAKDOWN")
    for category, amount in quote.breakdown.items():
        print(f"    {category:<26} {cur} {amount:>9.2f}  {amount / quote.total * 100:>5.1f}%")
    print(f"    {'TOTAL':<26} {cur} {quote.total:>9.2f}  ({quote.total / Decimal(str(area_m2 * 10.7639)):.2f} {cur}/sq ft)")
    for label, items in (("FLAGS", quote.flags), ("ASSUMPTIONS", quote.assumptions)):
        for item in items:
            print(f"  {label}: {item}")


if __name__ == "__main__":
    main()
