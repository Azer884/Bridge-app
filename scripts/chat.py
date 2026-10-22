"""Live multi-turn chat in the terminal against the RunPod model.

Usage:
  python scripts/chat.py [conversation_id]                 interactive
  python scripts/chat.py <id> "msg 1" "msg 2" ...          scripted
  Add --name="Sam Lee" --phone="+216 12 345 678" to simulate WhatsApp profile details
  (new conversations only; omit one to test the "ask at the end" path).
State is saved to data/conversations/<id>.json after every turn and the readable
transcript to logs/conversation_<id>.txt. Interactive: 'quit' stops, 'state' prints fields.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.assistant import handle_message  # noqa: E402
from src.conversation import ConversationStore  # noqa: E402
from src.guard import clean_profile_name, clean_profile_phone  # noqa: E402
from src.runpod_client import RunPodClient  # noqa: E402


def main():
    flags = {a.split("=", 1)[0]: a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--") and "=" in a}
    args = [a for a in sys.argv[1:] if not (a.startswith("--") and "=" in a)]
    conversation_id = args[0] if args else "demo"
    scripted = args[1:]
    config = json.loads((ROOT / "config" / "business_config.example.json").read_text())
    store = ConversationStore(ROOT / "data" / "conversations")
    state = store.load(conversation_id)
    if not state.history:
        channel = {"name": clean_profile_name(flags.get("--name")),
                   "phone": clean_profile_phone(flags.get("--phone"))}
        state.channel = {k: v for k, v in channel.items() if v}
    client = RunPodClient.from_env()

    transcript = ROOT / "logs" / f"conversation_{conversation_id}.txt"
    transcript.parent.mkdir(exist_ok=True)
    transcript.write_text("", encoding="utf-8")

    def log(line):
        print(line, flush=True)
        with transcript.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    messages = iter(scripted)
    while True:
        if scripted:
            text = next(messages, None)
            if text is None:
                break
        else:
            try:
                text = input("You: ").strip()
            except EOFError:
                break
            if text.lower() == "quit":
                break
            if text.lower() == "state":
                print(json.dumps(state.verified, indent=2))
                continue
        if not text:
            continue
        log(f"You: {text}")
        out = handle_message(state, text, config, client)
        store.save(state)
        log(f"Bot: {out.reply}")
        log(f"     [status={out.status} attempts={out.attempts} "
            f"missing={state.missing_required(config)}]")
        if out.problems:
            log(f"     [rejected: {out.problems}]")

    log(f"\nFinal verified fields: {json.dumps(state.verified)}")
    print(f"Saved to {transcript}")


if __name__ == "__main__":
    main()
