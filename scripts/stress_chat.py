"""Run chat scenarios against the live text model (RunPod, costs money: about $0.001 per model call) through the real
IncomingService, and write every reply to a JSON-lines file for reading.

usage: python scripts/stress_chat.py out.jsonl [prefix,prefix|all] [workers]
       python scripts/stress_chat.py out.jsonl time,colour 4
"""
import json
import re
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from src.events import IncomingEvent
from src.runpod_client import RunPodClient
from src.service import IncomingService
from src.store import SqliteStore
from stress_scenarios import S

CONFIG = json.loads((ROOT / "config" / "business_config.example.json").read_text(encoding="utf-8"))
STATS = {"calls": 0, "seconds": 0.0, "errors": 0}
LOCK = threading.Lock()


class Timed:
    def __init__(self, inner):
        self.inner = inner

    def chat(self, messages, sampling=None):
        start = time.time()
        try:
            return self.inner.chat(messages, sampling)
        except Exception:
            with LOCK:
                STATS["errors"] += 1
            raise
        finally:
            with LOCK:
                STATS["calls"] += 1
                STATS["seconds"] += time.time() - start


def flags(user, reply):
    out = []
    if not reply.strip():
        out.append("EMPTY")
    if re.search(r"\bmetres?\b", reply, re.I):
        out.append("METRES")
    if reply.count("?") > 1:
        out.append("MULTI_Q")
    if re.search(r"[{}]|extracted_fields|\bJSON\b|as an ai|language model", reply, re.I):
        out.append("LEAK")
    if len(reply) > 450:
        out.append("LONG")
    if re.search(r"RM\s?\d|\$\s?\d", reply):
        out.append("PRICE")
    return out


def run(name, client):
    directory = tempfile.TemporaryDirectory()
    store = SqliteStore(Path(directory.name) / "t.db")
    service = IncomingService(store, CONFIG, Timed(client))
    user = "60" + str(abs(hash(name)) % 10**9)
    turns = []
    for i, text in enumerate(S[name]):
        start = time.time()
        try:
            replies = service.handle(IncomingEvent(f"{name}-{i}", user, text=text, profile_name="Test Customer",
                                                   phone="+" + user))
            error = ""
        except Exception as err:
            replies, error = [], f"{type(err).__name__}: {err}"
        reply = "\n".join(replies)
        turns.append({"user": text[:300], "bot": reply, "secs": round(time.time() - start, 1), "flags": flags(text, reply),
                      "error": error})
    state = store.load(user)
    directory.cleanup()
    return {"name": name, "turns": turns, "stage": state.stage, "verified": state.verified, "lang": state.lang}


def main():
    out = Path(sys.argv[1])
    prefixes = sys.argv[2].split(",") if len(sys.argv) > 2 and sys.argv[2] != "all" else [""]
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    names = [n for n in S if any(n.startswith(p) for p in prefixes)]
    client = RunPodClient.from_env(timeout_s=420)
    started = time.time()
    with ThreadPoolExecutor(workers) as pool, out.open("w", encoding="utf-8") as fh:
        for result in pool.map(lambda n: run(n, client), names):
            fh.write(json.dumps(result, ensure_ascii=False) + "\n")
            fh.flush()
            print(result["name"], len(result["turns"]), flush=True)
    print(json.dumps({**STATS, "wall": round(time.time() - started), "scenarios": len(names)}))


main()
