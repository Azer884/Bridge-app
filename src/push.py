"""Push notifications to the owner's phone (the Gesir mobile app) through Expo's push service.

The app registers its Expo push token with POST /api/push/register. The service calls notify() when something needs
the owner: a customer asks for a person, an estimate waits for approval, a customer answers a booking slot or changes
the job after the estimate was sent. Sending happens on a background thread, so a slow or failing push never delays
the customer's reply. Expo needs no key; EXPO_ACCESS_TOKEN is used when the Expo project requires one.
"""
import json
import logging
import re
import threading
import urllib.error
import urllib.request

log = logging.getLogger("push")
EXPO_URL = "https://exp.host/--/api/v2/push/send"
TOKEN = re.compile(r"^(ExponentPushToken|ExpoPushToken)\[[A-Za-z0-9_\-]{10,100}\]$")
MAX_TOKENS = 20


class PushNotifier:
    def __init__(self, store, access_token=None, post=None):
        """post(url, payload, headers) -> parsed JSON reply; replaced in tests."""
        self.store, self.access_token = store, access_token
        self._post = post or _post

    def tokens(self):
        return list(self.store.get_setting("push_tokens", []) or [])

    def register(self, token, platform=""):
        if not isinstance(token, str) or not TOKEN.match(token):
            raise ValueError("not an Expo push token")
        tokens = [t for t in self.tokens() if t != token] + [token]
        self.store.set_setting("push_tokens", tokens[-MAX_TOKENS:])
        self.store.log_event("push_registered", f"{platform or 'phone'}: {len(tokens[-MAX_TOKENS:])} device(s)")

    def notify(self, title, body, data=None, wait=False):
        """Send to every registered phone. Returns the thread (or None when no phone is registered)."""
        tokens = self.tokens()
        if not tokens:
            return None
        messages = [{"to": t, "title": title[:100], "body": body[:240], "data": data or {}, "sound": "default",
                     "priority": "high", "channelId": "default"} for t in tokens]
        thread = threading.Thread(target=self._send, args=(messages,), daemon=True, name="push")
        thread.start()
        if wait:
            thread.join(30)
        return thread

    def _send(self, messages):
        headers = {"content-type": "application/json", "accept": "application/json"}
        if self.access_token:
            headers["authorization"] = f"Bearer {self.access_token}"
        try:
            reply = self._post(EXPO_URL, messages, headers)
        except Exception as err:
            log.warning("push failed: %s", err)
            self.store.log_event("push_failed", f"{type(err).__name__}: {err}")
            return
        tickets = reply.get("data") or []
        gone = [m["to"] for m, ticket in zip(messages, tickets)
                if ticket.get("status") == "error" and (ticket.get("details") or {}).get("error") == "DeviceNotRegistered"]
        if gone:                                    # the app was removed from that phone
            self.store.set_setting("push_tokens", [t for t in self.tokens() if t not in gone])
        errors = [ticket.get("message", "") for ticket in tickets if ticket.get("status") == "error"]
        self.store.log_event("push_failed" if errors and len(errors) == len(tickets) else "push_sent",
                             "; ".join(errors)[:200] if errors else f"{len(tickets)} device(s)")


def _post(url, payload, headers):
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)
