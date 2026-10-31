"""Send one customer message to the RunPod endpoint with the global system prompt.

Usage: python scripts/test_one.py "I want to paint my bedroom"
Tries the chat `messages` format first, then falls back to a plain `prompt`.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.prompt import load_system_prompt  # noqa: E402  (after the path is set)


def load_env(path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def post(url, key, payload):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as err:
        body = {"http_error": err.code, "body": err.read().decode("utf-8", "replace")}
    return body, time.time() - start


def get(url, key):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as err:
        return {"http_error": err.code, "body": err.read().decode("utf-8", "replace")}


def main():
    load_env(ROOT / ".env")
    key = os.environ.get("RUNPOD_API_KEY")
    endpoint = os.environ.get("RUNPOD_ENDPOINT_ID")
    if not key or not endpoint:
        sys.exit("Set RUNPOD_API_KEY and RUNPOD_ENDPOINT_ID in .env")

    message = sys.argv[1] if len(sys.argv) > 1 else "I want to paint my bedroom"
    system_prompt = load_system_prompt()
    url = f"https://api.runpod.ai/v2/{endpoint}/runsync"
    sampling = {"temperature": 0.2, "max_tokens": 300}

    attempts = [
        ("messages", {"input": {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
            "sampling_params": sampling,
        }}),
        ("prompt", {"input": {
            "prompt": f"{system_prompt}\n\nCustomer: {message}\n\nJSON:",
            "sampling_params": sampling,
        }}),
    ]
    for name, payload in attempts:
        start = time.time()
        body, _ = post(url, key, payload)
        # runsync gives up after ~90s; keep polling the job instead of resubmitting
        while body.get("status") in ("IN_QUEUE", "IN_PROGRESS") and time.time() - start < 600:
            print(f"  {body['status']} at {time.time() - start:.0f}s ...", flush=True)
            time.sleep(5)
            body = get(f"https://api.runpod.ai/v2/{endpoint}/status/{body['id']}", key)
        elapsed = time.time() - start
        print(f"--- format={name} elapsed={elapsed:.1f}s ---")
        reply = None
        try:
            reply = body["output"][0]["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            pass
        print(reply if reply else json.dumps(body, indent=2)[:4000])
        log_dir = ROOT / "logs"
        log_dir.mkdir(exist_ok=True)
        with (log_dir / "test_runs.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "format": name,
                "customer_message": message,
                "elapsed_s": round(elapsed, 1),
                "model_reply": reply,
                "raw": body,
            }) + "\n")
        if body.get("status") in ("COMPLETED", "IN_QUEUE", "IN_PROGRESS"):
            break  # only try the fallback format when the first was rejected or failed


if __name__ == "__main__":
    main()
