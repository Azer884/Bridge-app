"""The start command for the Gesir app on Replit (`.replit` runs `python scripts/start.py`).

GESIR_PORT overrides the port (used for local checks). The Orbyte-style dashboard is part of the app, served at /app, so
there is no second app to run.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

port = os.environ.get("GESIR_PORT", "8000")
os.execv(sys.executable, [sys.executable, "-m", "uvicorn", "src.server:create_app", "--factory",
                          "--host", "0.0.0.0", "--port", port])
