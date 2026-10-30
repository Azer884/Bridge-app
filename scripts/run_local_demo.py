"""Run the dashboard on this machine with a fake WhatsApp sender, so Approve works without a WhatsApp account.

    python scripts/run_local_demo.py            # http://localhost:8000/app, password: local-demo
    PORT=8001 BUSINESS_CONFIG=config/business_config.second.example.json DATABASE_PATH=data/second.db \
        python scripts/run_local_demo.py        # a second business on :8001 for the hub's business switcher

Data goes to data/bridge.db (SQLite). Nothing is sent anywhere: messages the app would send are printed here.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import uvicorn

from src.runpod_client import load_dotenv
from src.server import create_app


class PrintSender:
    """Stands in for WhatsAppSender: prints what would be sent to the customer and reports success."""
    last_error = ""

    def send_text(self, to, text):
        print(f"\n[fake WhatsApp -> {to}]\n{text}\n", flush=True)
        return True


def main():
    load_dotenv()
    env = dict(os.environ)
    env.setdefault("DASHBOARD_PASSWORD", "local-demo")
    env.setdefault("SESSION_SECRET", "local-session-secret")
    env["STT_WARMUP"] = "0"
    port = int(env.get("PORT", "8000"))
    env.setdefault("ORBYTE_SHARED_SECRET", "local-hub-secret")
    env.setdefault("ORBYTE_WEBHOOK_URL", f"http://localhost:9000/hub/webhook/{port}")     # the mock hub
    app = create_app(sender=PrintSender(), env=env)
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
