"""The start command for the Gesir app on Replit (`.replit` runs `python scripts/start.py`).

GESIR_PORT overrides the port (used for local checks). The Orbyte-style dashboard is part of the app, served at /app, so
there is no second app to run.

The phone-call agent (`voice_worker/`) runs beside the web app in the same process group when the app is published: it
starts after the web app is up, installs its own packages the first time, and is restarted if it stops. It talks to the
app over localhost. Switch it off with RUN_VOICE_WORKER=0, or on in the workspace with RUN_VOICE_WORKER=1. Without it the
app is exactly as before.
"""
import atexit
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

LIVEKIT_SECRETS = ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")
DEFAULT_VOICE = "a167e0f3-df7e-4d52-a9c3-f949145efdab"       # a Cartesia voice from config/trades/aircon.json, used when no character has one


def voice_worker_wanted(env=os.environ):
    """RUN_VOICE_WORKER decides. When it is not set the worker runs only in the published app (REPLIT_DEPLOYMENT) and only
    when the LiveKit secrets are there, so the workspace's Run button and a laptop never start a second agent."""
    flag = env.get("RUN_VOICE_WORKER")
    if flag is not None:
        return flag.strip().lower() not in ("", "0", "false", "no", "off")
    return bool(env.get("REPLIT_DEPLOYMENT")) and all(env.get(name) for name in LIVEKIT_SECRETS)


def worker_env(port, env=os.environ):
    """The worker's settings: the app on localhost, and a voice when none is set."""
    out = dict(env)
    out.setdefault("VOICE_BACKEND_URL", f"http://127.0.0.1:{port}")
    out.setdefault("VOICE_TTS_VOICE", DEFAULT_VOICE)
    out["PYTHONUNBUFFERED"] = "1"
    return out


def log(text):
    print(f"[voice] {text}", flush=True)


def install_packages():
    """The agent's packages (livekit-agents) are installed the first time; a failure is logged and tried again later."""
    try:
        import livekit.agents  # noqa: F401
        return True
    except ImportError:
        pass
    log("installing the voice agent's packages (first start only)")
    requirements = str(ROOT / "voice_worker" / "requirements.txt")
    for command in ([sys.executable, "-m", "pip", "install", "--quiet", "-r", requirements],
                    ["uv", "pip", "install", "--quiet", "--python", sys.executable, "-r", requirements]):
        try:
            if subprocess.run(command, check=False).returncode == 0:
                return True
        except OSError:
            continue
    log("could not install the packages")
    return False


def supervise(port):
    """Run the agent and start it again, a little later each time, if it stops."""
    time.sleep(15)                                         # the web app first: a slow install must not delay it
    failures, current = 0, {"proc": None}
    atexit.register(lambda: current["proc"] and current["proc"].terminate())
    while True:
        if install_packages():
            started = time.monotonic()
            log("starting the voice agent")
            current["proc"] = subprocess.Popen([sys.executable, "-m", "voice_worker.agent", "start"], env=worker_env(port))
            code = current["proc"].wait()
            failures = 0 if time.monotonic() - started > 120 else failures + 1
            log(f"the voice agent stopped (code {code})")
        else:
            failures += 1
        time.sleep(min(60, 5 * (failures + 1)))


def main():
    port = os.environ.get("GESIR_PORT", "8000")
    if voice_worker_wanted():
        threading.Thread(target=supervise, args=(port,), daemon=True, name="voice-worker").start()
    import uvicorn
    uvicorn.run("src.server:create_app", factory=True, host="0.0.0.0", port=int(port))


if __name__ == "__main__":
    main()
