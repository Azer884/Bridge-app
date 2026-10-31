"""One start command for every Replit app made from this repository, so `.replit` never has to differ between them.

    python scripts/start.py                 # the Gesir app (the default)
    ORBYTE_HUB=1 python scripts/start.py    # the simulated Orbyte hub instead

On Replit, set the secret ORBYTE_HUB=1 only in the hub app. The Gesir app needs nothing. Both listen on port 8000, which
`.replit` maps to port 80. GESIR_PORT overrides the Gesir port (used for local checks).
"""
import os
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

if os.environ.get("ORBYTE_HUB") == "1":
    os.environ.setdefault("PORT", "8000")           # a set PORT makes the hub listen on every address
    runpy.run_path(str(ROOT / "scripts" / "mock_orbyte.py"), run_name="__main__")
else:
    port = os.environ.get("GESIR_PORT", "8000")
    os.execv(sys.executable, [sys.executable, "-m", "uvicorn", "src.server:create_app", "--factory",
                              "--host", "0.0.0.0", "--port", port])
