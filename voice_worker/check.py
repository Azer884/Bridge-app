"""Pre-flight check for the voice worker: are the settings there, can it reach the assistant, are the LiveKit keys accepted.

    python -m voice_worker.check

Values are never printed, only whether they are set and what each service answered.
"""
import asyncio
import json
import os
import sys
import urllib.error
import urllib.request

from dotenv import load_dotenv

REQUIRED = ["LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "VOICE_BACKEND_URL", "INCOMING_API_KEY",
            "VOICE_TTS_VOICE"]


def get(url, key=None):
    request = urllib.request.Request(url, headers={"x-api-key": key} if key else {})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.read().decode()[:300]
    except urllib.error.HTTPError as err:
        return err.code, ""
    except (urllib.error.URLError, TimeoutError) as err:
        return 0, str(err)


async def livekit_accepts_the_keys():
    from livekit import api
    client = api.LiveKitAPI()                       # reads LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET
    try:
        await client.room.list_rooms(api.ListRoomsRequest())
        return ""
    except Exception as err:                        # noqa: BLE001 - any failure is the answer
        return f"{type(err).__name__}: {err}"[:200]
    finally:
        await client.aclose()


def main():
    load_dotenv(".env.local")
    load_dotenv()
    problems = 0
    for name in REQUIRED:
        present = bool(os.environ.get(name))
        print(f"{'ok     ' if present else 'MISSING'} {name}")
        problems += not present
    if problems:
        print(f"\n{problems} setting(s) missing: add them to .env.local, then run this again.")
        return 1
    base = os.environ["VOICE_BACKEND_URL"].rstrip("/")
    status, _ = get(base + "/health")
    print(f"{'ok     ' if status == 200 else 'FAILED '} the assistant answers at {base} (HTTP {status})")
    problems += status != 200
    status, body = get(base + "/api/voice/health", os.environ["INCOMING_API_KEY"])
    if status == 200:
        print(f"ok      INCOMING_API_KEY is accepted; voice-note model: {json.loads(body)}")
    else:
        print(f"FAILED  INCOMING_API_KEY was refused or the app is down (HTTP {status})")
        problems += 1
    error = asyncio.run(livekit_accepts_the_keys())
    print(f"{'ok     ' if not error else 'FAILED '} LiveKit accepts the keys" + (f": {error}" if error else ""))
    problems += bool(error)
    print("\nReady: python -m voice_worker.agent dev" if not problems else f"\n{problems} problem(s) above.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
