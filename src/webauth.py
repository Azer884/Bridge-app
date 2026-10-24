"""Login for the hosted dashboard: one shared password, a signed cookie, and a limit on wrong guesses.

The API already accepts the x-api-key header (for n8n, scripts and the native app). A browser cannot keep that key
secret, so the web dashboard signs in with DASHBOARD_PASSWORD instead and gets a cookie that the API also accepts.
"""
import hashlib
import hmac
import time
from html import escape

COOKIE = "gesir_session"
MAX_AGE = 12 * 3600
MAX_FAILURES, WINDOW = 5, 600           # five wrong passwords per ten minutes, per address


def _sign(secret, expires):
    return hmac.new(secret, f"dashboard:{expires}".encode(), hashlib.sha256).hexdigest()


def make_cookie(secret, now=None):
    expires = int((now or time.time()) + MAX_AGE)
    return f"{expires}.{_sign(secret, expires)}"


def valid_cookie(secret, value, now=None):
    if not secret or not value or "." not in value:
        return False
    expires, _, signature = value.partition(".")
    if not expires.isdigit() or int(expires) < (now or time.time()):
        return False
    return hmac.compare_digest(signature, _sign(secret, expires))


def safe_next(target):
    """Only paths on this site: "/app/quotes" yes, "https://evil.example" and "//evil.example" no."""
    if isinstance(target, str) and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return "/app"


class LoginLimiter:
    def __init__(self):
        self.failures = {}

    def blocked(self, who, now=None):
        now = now or time.time()
        recent = [t for t in self.failures.get(who, []) if now - t < WINDOW]
        self.failures[who] = recent
        return len(recent) >= MAX_FAILURES

    def fail(self, who, now=None):
        self.failures.setdefault(who, []).append(now or time.time())

    def clear(self, who):
        self.failures.pop(who, None)


def login_page(next_path="/app", error="", enabled=True):
    note = error or ("" if enabled else "The dashboard password is not set on the server yet (DASHBOARD_PASSWORD).")
    form = ("" if not enabled else
            '<input type="password" name="password" placeholder="Password" autocomplete="current-password" '
            'autofocus required><button type="submit">Sign in</button>')
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sign in</title>
<style>
:root {{ --bg:#f6f7f9; --card:#fff; --ink:#15171a; --muted:#5b6370; --line:#d9dde3; --brand:#0f6fff; --bad:#b3261e; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#0f1115; --card:#181b21; --ink:#f2f4f7; --muted:#9aa3b2; --line:#2a2f38; --brand:#5b9bff; --bad:#ff8a80; }} }}
* {{ box-sizing:border-box }} body {{ margin:0; min-height:100vh; display:grid; place-items:center; background:var(--bg); color:var(--ink);
font:16px/1.4 system-ui, sans-serif; padding:16px }}
form {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:28px; width:100%; max-width:360px; display:grid; gap:12px }}
h1 {{ margin:0 0 4px; font-size:20px }} p {{ margin:0; color:var(--muted); font-size:14px }} .err {{ color:var(--bad) }}
input,button {{ font:inherit; padding:11px 12px; border-radius:8px; border:1px solid var(--line); background:var(--bg); color:var(--ink) }}
button {{ background:var(--brand); color:#fff; border:0; cursor:pointer; font-weight:600 }}
</style></head><body>
<form method="post" action="/login">
<h1>Gesir dashboard</h1><p>Sign in to review quotes and manage the calendar.</p>
<input type="hidden" name="next" value="{escape(next_path, quote=True)}">
{form}
<p class="err" role="alert">{escape(note)}</p>
</form></body></html>"""
