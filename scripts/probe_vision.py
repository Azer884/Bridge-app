"""Send one photo to the vision endpoint and show the raw and validated result.

Usage: python scripts/probe_vision.py path/to/photo.jpg
Needs RUNPOD_API_KEY and RUNPOD_VISION_ENDPOINT_ID in .env.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.parsing import ParseError, extract_json  # noqa: E402
from src.runpod_client import RunPodClient  # noqa: E402
from src.vision import assess_image, image_message  # noqa: E402

MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    path = Path(sys.argv[1])
    mime = MIME.get(path.suffix.lower())
    if mime is None:
        sys.exit(f"unsupported file type {path.suffix}")
    image = path.read_bytes()
    client = RunPodClient.from_env("RUNPOD_VISION_ENDPOINT_ID", key_var="RUNPOD_VISION_API_KEY", sampling={"temperature": 0.1, "max_tokens": 300})

    start = time.time()
    image_message(image, mime)  # fails early on bad size or type
    assessment, raw = assess_image(client, image, mime)
    print(f"elapsed {time.time() - start:.1f}s")
    print("RAW MODEL OUTPUT:\n" + raw)
    try:
        print("PARSED JSON:", json.dumps(extract_json(raw)))
    except ParseError as err:
        print("PARSED JSON: none -", err)
    print("VALIDATED ASSESSMENT:", assessment)

    out = ROOT / "logs" / "vision_runs.jsonl"
    out.parent.mkdir(exist_ok=True)
    with out.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"image": path.name, "raw": raw, "assessment": str(assessment)}) + "\n")


if __name__ == "__main__":
    main()
