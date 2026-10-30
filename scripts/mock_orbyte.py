"""A local stand-in for the Orbyte hub, to see how Gesir looks and behaves as a module inside it.

    python scripts/run_local_demo.py     # terminal 1: business A on http://localhost:8000
    PORT=8001 BUSINESS_CONFIG=config/business_config.second.example.json DATABASE_PATH=data/second.db \\
        python scripts/run_local_demo.py # terminal 2 (optional): business B on :8001
    python scripts/mock_orbyte.py        # terminal 3: mock hub on http://localhost:9000

What the hub does, as Orbyte would: an Approve queue with roles, an activity log, Clients, a Wallet that is charged per
approved quote, signed events from the module, a benefit card with its assumptions, and the Gesir dashboard embedded
as a module. It reads the module's API on the server side (the key never reaches the browser).
Both run on localhost, so the dashboard's login cookie works inside the iframe (same site, different port).
The layout only imitates Orbyte's navigation; it uses no Orbyte code or branding assets.
"""
import json
import os
import sys
import time
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

from src import orbyte
from src.runpod_client import load_dotenv

load_dotenv()
KEY = os.environ.get("INCOMING_API_KEY", "")
SECRET = os.environ.get("ORBYTE_SHARED_SECRET", "local-hub-secret")
CREDITS_PER_QUOTE = 1
TENANTS = {                                      # business id -> module URL (one Gesir instance per business)
    "8000": {"name": "Example Painting", "url": "http://localhost:8000"},
    "8001": {"name": "Berus Biru Painting", "url": "http://localhost:8001"},
}
wallet = {t: 100 for t in TENANTS}
events = []                                      # signed events received from the module, newest first
esign = {}                                       # user_id -> "sent" (a mock: no e-sign provider is called)

app = FastAPI(title="Mock Orbyte hub")


def tenant(tid):
    if tid not in TENANTS:
        raise HTTPException(404, "unknown business")
    return TENANTS[tid]


def gesir(tid, path, method="GET", body=None, role="admin", user="Hub"):
    headers = {"x-api-key": KEY, "content-type": "application/json", "x-orbyte-role": role, "x-orbyte-user": user}
    req = urlrequest.Request(tenant(tid)["url"].replace("localhost", "127.0.0.1") + path,    # skips a slow IPv6 attempt on Windows
                              method=method, headers=headers,
                             data=json.dumps(body).encode() if body is not None else None)
    try:
        with urlrequest.urlopen(req, timeout=15) as res:
            return json.loads(res.read() or b"null")
    except urlerror.HTTPError as err:            # pass the module's own refusal (403, 409...) on to the screen
        detail = json.loads(err.read() or b"{}").get("detail", err.reason)
        raise HTTPException(err.code, detail if isinstance(detail, str) else json.dumps(detail))
    except Exception as err:                     # the hub stays up when a module is down
        raise HTTPException(502, f"The module on {tenant(tid)['url']} is not reachable: {err}")


def who(request):
    return request.headers.get("x-hub-role", "admin"), request.headers.get("x-hub-user", "Azer")


@app.get("/hub/tenants")
def tenants():
    return [{"id": k, **v, "credits": wallet[k]} for k, v in TENANTS.items()]


@app.get("/hub/{tid}/pending")
def pending(tid: str):
    quotes = gesir(tid, "/api/quotes?status=pending_approval")["quotes"] + \
        gesir(tid, "/api/quotes?status=needs_inspection")["quotes"]
    return [{"id": q["user_id"], "customer": q["customer"], "status": q["status"],
             "total": (q.get("quote") or {}).get("total"), "currency": (q.get("quote") or {}).get("currency", "MYR"),
             "age": q.get("updated_at")} for q in quotes]


@app.get("/hub/{tid}/sent")
def sent(tid: str):
    rows = gesir(tid, "/api/quotes?status=approved")["quotes"] + gesir(tid, "/api/quotes?status=completed")["quotes"]
    return [{"id": q["user_id"], "customer": q["customer"], "status": q["status"],
             "total": (q.get("quote") or {}).get("approved_total") or (q.get("quote") or {}).get("total"),
             "esign": esign.get(q["user_id"])} for q in rows]


@app.get("/hub/{tid}/benefit")
def benefit(tid: str):
    done = len(gesir(tid, "/api/quotes?status=approved")["quotes"]) + len(gesir(tid, "/api/quotes?status=completed")["quotes"])
    rejected = len(gesir(tid, "/api/quotes?status=rejected")["quotes"])
    return {"approved": done, "rejected": rejected}


@app.get("/hub/{tid}/clients")
def clients(tid: str):
    return [{"id": c["user_id"], "name": c["name"], "phone": c["phone"], "orders": c["orders"]}
            for c in gesir(tid, "/api/customers")["customers"]]


@app.get("/hub/{tid}/audit")
def audit(tid: str):
    return gesir(tid, "/api/audit?limit=40")["entries"]


@app.post("/hub/{tid}/approve/{user_id}")
def approve(tid: str, user_id: str, request: Request):
    role, user = who(request)
    out = gesir(tid, f"/api/quotes/{user_id}/approve", "POST", {}, role, user)
    wallet[tid] -= CREDITS_PER_QUOTE                # usage-based: one credit per approved quote
    return out


@app.post("/hub/{tid}/reject/{user_id}")
async def reject(tid: str, user_id: str, request: Request):
    role, user = who(request)
    body = await request.json()
    return gesir(tid, f"/api/quotes/{user_id}/reject", "POST", {"reason": body.get("reason", "")}, role, user)


@app.post("/hub/{tid}/esign/{user_id}")
def send_for_signature(tid: str, user_id: str):
    esign[user_id] = "sent"                         # mock: a real hub would hand the quote to its e-sign service
    events.insert(0, {"type": "esign.requested (hub)", "at": time.time(), "data": {"user_id": user_id}, "ok": True})
    return {"esign": "sent"}


@app.post("/hub/webhook/{tid}")
async def webhook(tid: str, request: Request):
    raw = await request.body()
    ok = orbyte.sign(SECRET, raw) == request.headers.get("x-orbyte-signature")
    event = json.loads(raw or b"{}")
    events.insert(0, {"type": event.get("type"), "at": event.get("at"), "data": event.get("data"), "ok": ok, "tenant": tid})
    del events[100:]
    if not ok:
        raise HTTPException(401, "bad signature")
    return {"received": True}


@app.get("/hub/events")
def feed():
    return events[:40]


@app.get("/")
def home():
    return HTMLResponse((Path(__file__).with_name("mock_orbyte.html")).read_text(encoding="utf-8"))


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("HUB_PORT", "9000")))
