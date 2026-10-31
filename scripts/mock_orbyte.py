"""A local stand-in for the Orbyte hub, built to follow the real Orbyte's layout and behaviour (organization switcher, the
Organization menu, Pending Actions with Submit, Review and Approve tabs, Users with Role, Approver and Reviewer, a Wallet of
credits with a transaction list, Settings & Notifications, Organization Settings with Integrations).

    python scripts/run_local_demo.py     # terminal 1: business A on http://localhost:8000
    PORT=8001 BUSINESS_CONFIG=config/business_config.second.example.json DATABASE_PATH=data/second.db \\
        python scripts/run_local_demo.py # terminal 2 (optional): business B on :8001
    python scripts/mock_orbyte.py        # terminal 3: the hub on http://localhost:9000

Only things the real Orbyte has are shown. What it does not publish is an assumption, listed in docs/ORBYTE.md: that a module
sends signed events to the hub, that the hub passes the signed-in user's role to the module, that Orbyte projects can have a
source ("Gesir") and that the module can be opened in a frame. Users and roles are simulated, as the challenge rules allow.
Hosted: set HUB_TENANTS, INCOMING_API_KEY (the module's key) and ORBYTE_SHARED_SECRET, and run this file; see docs/ORBYTE.md.
It reads the module's API on the server side (the key never reaches the browser). It uses no Orbyte code, logo or images.
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
CREDITS_PER_ESTIMATE = 1
OPENING_CREDITS = 100
TENANT_ERROR = ""


def _tenants():
    """One organization per Gesir business. HUB_TENANTS is a JSON list such as
    [{"id": "hrissa", "name": "Hrissa", "url": "https://gesir-ai.replit.app"}]; without it the two local demo businesses are used.
    A value that is not valid JSON does not crash the server (a crash loop hides the reason): the hub starts and says what is wrong."""
    global TENANT_ERROR
    raw = (os.environ.get("HUB_TENANTS") or "").strip()
    if raw:
        for text in (raw, "[" + raw + "]"):                # a single object, or objects separated by commas, also work
            try:
                items = json.loads(text)
                items = items if isinstance(items, list) else [items]
                return {t["id"]: {"name": t["name"], "url": t["url"].rstrip("/")} for t in items}
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
        TENANT_ERROR = ('HUB_TENANTS is not valid. It must be one JSON list like '
                        '[{"id":"hrissa","name":"Hrissa","url":"https://gesir-ai.replit.app"}]')
        return {}
    return {"8000": {"name": "Example Painting", "url": "http://localhost:8000"},
            "8001": {"name": "Berus Biru Painting", "url": "http://localhost:8001"}}


TENANTS = _tenants()
USERS = [                                        # simulated people; the hub, not the browser, decides what each may do
    {"id": "azer", "name": "Azer Hamdaoui", "email": "azer@example.com", "role": "Company Admin", "approver": False, "reviewer": False},
    {"id": "aisha", "name": "Aisha Rahman", "email": "aisha@example.com", "role": "Member", "approver": True, "reviewer": False},
    {"id": "mei", "name": "Mei Lin", "email": "mei@example.com", "role": "Member", "approver": False, "reviewer": True},
]
STATUS_LABEL = {"collecting": "Collecting details", "pending_approval": "Needs approval", "needs_inspection": "Needs inspection",
                "approved": "Approved", "completed": "Completed", "rejected": "Rejected"}
wallet = {t: {"credits": OPENING_CREDITS, "transactions": []} for t in TENANTS}
events = []                                      # signed events received from the module, newest first

app = FastAPI(title="Mock Orbyte hub")


def tenant(tid):
    if tid not in TENANTS:
        raise HTTPException(404, "unknown organization")
    return TENANTS[tid]


def user_of(request):
    return next((u for u in USERS if u["id"] == request.headers.get("x-hub-user")), USERS[0])


def module_role(user):
    """The role the hub passes to the module: Company Admin is admin, a Member marked Approver approves, anyone else reads."""
    if user["role"] == "Company Admin":
        return "admin"
    return "approver" if user["approver"] else "reviewer"


def gesir(tid, path, method="GET", body=None, user=None):
    user = user or USERS[0]
    headers = {"x-api-key": KEY, "content-type": "application/json", "x-orbyte-role": module_role(user),
               "x-orbyte-user": user["name"]}
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


def project(q):
    quote = q.get("quote") or {}
    return {"id": q["user_id"], "name": f"Repaint for {q['customer']}", "client": q["customer"], "phone": q.get("phone"),
            "status": q["status"], "status_label": STATUS_LABEL.get(q["status"], q["status"]), "source": "Gesir",
            "amount": quote.get("approved_total") or quote.get("total"), "currency": quote.get("currency", "MYR"),
            "updated": q.get("updated_at"), "address": (q.get("job") or {}).get("address")}


@app.get("/hub/tenants")
def tenants():
    if TENANT_ERROR:
        raise HTTPException(500, TENANT_ERROR)
    return [{"id": k, **v, "credits": wallet[k]["credits"]} for k, v in TENANTS.items()]


@app.get("/hub/users")
def users():
    return [{**u, "module_role": module_role(u)} for u in USERS]


@app.get("/hub/{tid}/pending")
def pending(tid: str):
    """Everything waiting for a person: estimates to approve or inspect, and customers who asked for a human or changed
    something (the module flags them). Each row says which kind of action it is."""
    rows = gesir(tid, "/api/pipeline")["quotes"]
    out = []
    for q in rows:
        if q["status"] in ("pending_approval", "needs_inspection"):
            out.append({**project(q), "kind": "approve"})
        elif q["status"] not in ("rejected", "completed") and (q.get("needs_human") or q.get("attention")):
            out.append({**project(q), "kind": "reply"})
    return out


@app.get("/hub/{tid}/projects")
def projects(tid: str):
    return [project(q) for q in gesir(tid, "/api/pipeline")["quotes"]]


@app.get("/hub/{tid}/project/{user_id}")
def project_detail(tid: str, user_id: str, request: Request):
    detail = gesir(tid, f"/api/quotes/{user_id}", user=user_of(request))
    return {"project": project(detail), "job": detail.get("job"), "audit": detail.get("audit", []),
            "reason": ((detail.get("quote") or {}).get("rejected") or {}).get("reason")}


@app.get("/hub/{tid}/clients")
def clients(tid: str):
    return [{"id": c["user_id"], "name": c["name"], "phone": c["phone"], "projects": len(c["orders"])}
            for c in gesir(tid, "/api/customers")["customers"]]


@app.get("/hub/{tid}/wallet")
def wallet_of(tid: str):
    tenant(tid)
    return wallet[tid]


@app.post("/hub/{tid}/approve/{user_id}")
def approve(tid: str, user_id: str, request: Request):
    user = user_of(request)
    out = gesir(tid, f"/api/quotes/{user_id}/approve", "POST", {}, user)
    box = wallet[tid]
    box["credits"] -= CREDITS_PER_ESTIMATE               # usage-based: one credit per approved estimate
    box["transactions"].insert(0, {"at": time.time(), "type": "Usage", "change": -CREDITS_PER_ESTIMATE,
                                   "balance": box["credits"], "details": f"Gesir: estimate approved for {user_id}"})
    return out


@app.post("/hub/{tid}/reject/{user_id}")
async def reject(tid: str, user_id: str, request: Request):
    body = await request.json()
    return gesir(tid, f"/api/quotes/{user_id}/reject", "POST", {"reason": body.get("reason", "")}, user_of(request))


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
    # on a host such as Replit the platform sets PORT and the hub must listen on every address
    hosted = bool(os.environ.get("PORT"))
    uvicorn.run(app, host="0.0.0.0" if hosted else "127.0.0.1", port=int(os.environ.get("PORT") or os.environ.get("HUB_PORT", "9000")))
