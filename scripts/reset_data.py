"""Erase every customer's data from the database this app uses, so it starts empty.

    python scripts/reset_data.py            # shows what would be erased and stops
    python scripts/reset_data.py --yes      # erases it. This cannot be undone.

Run it where the data lives: in the Replit shell for the published app (it reads DATABASE_URL), or on your machine for the
local demo (data/bridge.db, or DATABASE_PATH). It erases chats, photos' message records, bookings, the activity log, the
event trail and the queue of events for an Orbyte hub. It keeps settings (personas, the linked WhatsApp number, push tokens).
Take a database backup first if there is anything you may want again.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.runpod_client import load_dotenv
from src.store import make_store

TABLES = ["conversations", "messages", "bookings", "audit", "processed_messages", "processed_call_events", "events"]


def main():
    load_dotenv(ROOT / ".env")
    store = make_store(dict(os.environ), ROOT / "data" / "bridge.db")
    where = "PostgreSQL (DATABASE_URL)" if os.environ.get("DATABASE_URL") else str(os.environ.get("DATABASE_PATH") or ROOT / "data" / "bridge.db")
    with store._conn() as conn:
        counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}
    print(f"Database: {where}")
    for table, n in counts.items():
        print(f"  {table}: {n}")
    if "--yes" not in sys.argv:
        print("\nNothing was erased. Run again with --yes to erase all of the above.")
        return
    with store._conn() as conn:
        for table in TABLES:
            conn.execute(f"DELETE FROM {table}")
    store.set_setting("orbyte_outbox", [])
    print("\nErased. The app starts with no customers.")


if __name__ == "__main__":
    main()
