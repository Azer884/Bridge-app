"""The link to an Orbyte-style hub: who is acting (a role the hub passes in) and signed events sent back to it.

Orbyte has no public API, so this is an assumed interface, documented in docs/ORBYTE.md. Roles arrive in the
x-orbyte-role header on requests that carry the API key; the dashboard's own login counts as admin.
"""
import hashlib
import hmac
import json
import logging
import queue
import threading
import time
from urllib import request as urlrequest

log = logging.getLogger("gesir.orbyte")

ROLES = ("admin", "approver", "reviewer")
CAN_DECIDE = ("admin", "approver")              # who may approve or reject an estimate


def acting(role_header, user_header):
    """(role, name) of the caller. A missing role is admin, so scripts and the mobile app keep working;
    an unknown role gets nothing (a reviewer-level read), never more than it asked for."""
    role = (role_header or "admin").strip().lower()
    return (role if role in ROLES else "reviewer"), (user_header or "").strip()[:60] or None


def sign(secret, raw):
    return "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


class Emitter:
    """Sends events to the hub from a background thread so a slow hub never blocks an approval. Events wait in the
    store (setting "orbyte_outbox") until the hub has taken them, so a restart loses nothing. Failed sends are retried
    a few times; after that the event stays queued for the next start and a failure is logged as an event."""
    RETRIES = (0, 2, 10)
    KEY = "orbyte_outbox"
    MAX_QUEUED = 200

    def __init__(self, url, secret, store=None, post=None):
        self.url, self.secret, self.store = url, secret or "", store
        self.post = post or self._post
        self.queue = queue.Queue()
        self.lock = threading.Lock()
        if url:
            for event in (self._saved() if store else []):      # events a restart interrupted
                self.queue.put(event)
            threading.Thread(target=self._run, daemon=True, name="orbyte-emitter").start()

    def _saved(self):
        return list(self.store.get_setting(self.KEY, []) or [])

    def _save(self, change):
        if not self.store:
            return
        with self.lock:
            events = change(self._saved())
            self.store.set_setting(self.KEY, events[-self.MAX_QUEUED:])

    def emit(self, kind, data):
        if self.url:
            event = {"id": f"evt-{time.time_ns()}", "type": kind, "at": time.time(), "data": data}
            self._save(lambda events: events + [event])
            self.queue.put(event)

    def pending(self):
        return self._saved()

    def _post(self, raw, headers):
        req = urlrequest.Request(self.url, data=raw, headers=headers, method="POST")
        with urlrequest.urlopen(req, timeout=10) as res:
            return res.status

    def _run(self):
        while True:
            event = self.queue.get()
            raw = json.dumps(event).encode()
            headers = {"content-type": "application/json", "x-orbyte-signature": sign(self.secret, raw)}
            for wait in self.RETRIES:
                time.sleep(wait)
                try:
                    self.post(raw, headers)
                    self._save(lambda events: [e for e in events if e["id"] != event["id"]])
                    break
                except Exception as err:
                    last = str(err)[:120]
            else:
                log.warning("orbyte event %s not delivered: %s", event["type"], last)
                if self.store:
                    self.store.log_event("orbyte_send_failed", f"{event['type']}: {last}")


# People and credits the Orbyte-style dashboard shows. Orbyte publishes neither, so both are assumptions (docs/ORBYTE.md).
USERS = [
    {"id": "azer", "name": "Azer Hamdaoui", "email": "azer@example.com", "role": "Company Admin", "approver": False, "reviewer": False},
    {"id": "aisha", "name": "Aisha Rahman", "email": "aisha@example.com", "role": "Member", "approver": True, "reviewer": False},
    {"id": "mei", "name": "Mei Lin", "email": "mei@example.com", "role": "Member", "approver": False, "reviewer": True},
]
OPENING_CREDITS = 100
CREDITS_PER_ESTIMATE = 1
WALLET_KEY = "wallet"


def module_role(user):
    """The role a person has in Gesir: a Company Admin is admin, a Member marked Approver approves, anyone else reads."""
    if user["role"] == "Company Admin":
        return "admin"
    return "approver" if user["approver"] else "reviewer"


def users():
    return [{**u, "module_role": module_role(u)} for u in USERS]


def wallet(store):
    return store.get_setting(WALLET_KEY, None) or {"credits": OPENING_CREDITS, "transactions": []}


def charge_estimate(store, user_id, name):
    """One credit per estimate a person approves. Kept in the store, so it survives a restart."""
    box = wallet(store)
    box["credits"] -= CREDITS_PER_ESTIMATE
    box["transactions"] = ([{"at": time.time(), "type": "Usage", "change": -CREDITS_PER_ESTIMATE, "balance": box["credits"],
                             "details": f"Estimate approved for {user_id} by {name or 'someone'}"}] + box["transactions"])[:100]
    store.set_setting(WALLET_KEY, box)
    return box
