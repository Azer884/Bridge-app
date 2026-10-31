"""Accounts for the hosted dashboard: sign up, sign in, a signed cookie, and a limit on wrong guesses.

The API already accepts the x-api-key header (for n8n, scripts and the native app). A browser cannot keep that key
secret, so the web dashboard signs in with an account instead and gets a cookie that the API also accepts.
Accounts are kept in the store's settings table, so they live in PostgreSQL on Replit and in SQLite locally.
"""
import hashlib
import hmac
import json
import re
import secrets
import time
from html import escape

COOKIE = "gesir_session"
MAX_AGE = 12 * 3600
MAX_FAILURES, WINDOW = 5, 600           # five wrong passwords per ten minutes, per address
TRADES = {"painting": "Painting", "aircon": "Aircon servicing"}
MIN_PASSWORD = 8
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _sign(secret, expires, email=""):
    message = f"dashboard:{expires}" + (f":{email}" if email else "")
    return hmac.new(secret, message.encode(), hashlib.sha256).hexdigest()


def make_cookie(secret, now=None, email=""):
    """expires.signature, or expires.hex(email).signature when the cookie names the signed-in account."""
    expires = int((now or time.time()) + MAX_AGE)
    if email:
        return f"{expires}.{email.encode().hex()}.{_sign(secret, expires, email)}"
    return f"{expires}.{_sign(secret, expires)}"


def read_cookie(secret, value, now=None):
    """(valid, email) of a session cookie; email is "" for a cookie that names nobody."""
    if not secret or not value or "." not in value:
        return False, ""
    expires, _, rest = value.partition(".")
    if not expires.isdigit() or int(expires) < (now or time.time()):
        return False, ""
    email, signature = "", rest
    if "." in rest:
        hexed, _, signature = rest.partition(".")
        try:
            email = bytes.fromhex(hexed).decode()
        except ValueError:
            return False, ""
    return hmac.compare_digest(signature, _sign(secret, expires, email)), email


def valid_cookie(secret, value, now=None):
    return read_cookie(secret, value, now)[0]


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


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=salt.encode(), n=2 ** 14, r=8, p=1).hex()
    return f"{salt}${digest}"


def check_password(password, stored):
    salt, _, digest = stored.partition("$")
    return hmac.compare_digest(hash_password(password, salt).partition("$")[2], digest)


class Accounts:
    """Dashboard accounts, kept as one JSON setting: email -> name, business, trade, password hash.

    The trade is only recorded for now; nothing in the assistant changes with it, both trades work for every account."""
    KEY = "accounts"

    def __init__(self, store):
        self.store = store

    def _all(self):
        try:
            return json.loads(self.store.get_setting(self.KEY) or "{}")
        except ValueError:
            return {}

    def get(self, email):
        account = self._all().get((email or "").strip().lower())
        return {k: v for k, v in account.items() if k != "password"} if account else None

    def create(self, name, email, password, business, trade):
        """The new account, or a ValueError with the sentence to show the person."""
        name, business, email = (name or "").strip(), (business or "").strip(), (email or "").strip().lower()
        if not 2 <= len(name) <= 80:
            raise ValueError("Enter your name.")
        if not business or len(business) > 120:
            raise ValueError("Enter your business name.")
        if not _EMAIL.match(email) or len(email) > 120:
            raise ValueError("Enter a valid email address.")
        if len(password or "") < MIN_PASSWORD:
            raise ValueError(f"Choose a password of at least {MIN_PASSWORD} characters.")
        if trade not in TRADES:
            raise ValueError("Choose your trade.")
        accounts = self._all()
        if email in accounts:
            raise ValueError("That email already has an account. Sign in instead.")
        accounts[email] = {"name": name, "email": email, "business": business, "trade": trade,
                           "created": int(time.time()), "password": hash_password(password)}
        self.store.set_setting(self.KEY, json.dumps(accounts))
        return self.get(email)

    def authenticate(self, email, password):
        account = self._all().get((email or "").strip().lower())
        if account and check_password(password or "", account["password"]):
            return self.get(email)
        if not account:
            hash_password(password or "")       # an unknown email costs the same time as a wrong password
        return None


def auth_page(mode="login", next_path="/app", error="", values=None):
    values = values or {}
    v = lambda key: escape(values.get(key, ""), quote=True)
    signup = mode == "signup"
    options = "".join(
        f'<option value="{key}"{" selected" if values.get("trade") == key else ""}>{escape(label)}</option>'
        for key, label in TRADES.items())
    chosen = "" if values.get("trade") in TRADES else " selected"
    fields = (
        f'<label>Your name<input name="name" value="{v("name")}" autocomplete="name" required></label>'
        f'<label>Business name<input name="business" value="{v("business")}" autocomplete="organization" required></label>'
        f'<label>Your trade<select name="trade" required><option value="" disabled{chosen}>Choose your trade</option>'
        f'{options}</select></label>'
    ) if signup else ""
    heading, lead = (("Create your account", "Set up Gesir for your business.") if signup
                     else ("Gesir dashboard", "Sign in to review quotes and manage the calendar."))
    button = "Create account" if signup else "Sign in"
    n = escape(next_path, quote=True)
    other = (f'Already have an account? <a href="/login?next={n}">Sign in</a>' if signup
             else f'New here? <a href="/signup?next={n}">Create an account</a>')
    autofocus = "" if signup else "autofocus "
    password_attrs = 'autocomplete="new-password" minlength="%d"' % MIN_PASSWORD if signup else 'autocomplete="current-password"'
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{button}</title>
<link href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;600;700&display=swap" rel="stylesheet">
<style>
:root {{ --bg:#f5f8fe; --card:#fff; --ink:#1c3153; --muted:#64748b; --line:#e2e8f0; --brand:#0767e8; --bad:#b3261e; }}
* {{ box-sizing:border-box }} body {{ margin:0; min-height:100vh; display:grid; place-items:center; background:var(--bg); color:var(--ink);
font:15px/1.45 "Public Sans", system-ui, sans-serif; padding:16px }}
form {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:28px; width:100%; max-width:380px; display:grid; gap:12px;
box-shadow:0 24px 60px -32px rgba(15,30,60,.35) }}
h1 {{ margin:0 0 2px; font-size:24px; font-weight:600 }} p {{ margin:0; color:var(--muted); font-size:14px }} .err {{ color:var(--bad) }}
label {{ display:grid; gap:4px; font-size:13px; font-weight:600 }}
input,select,button {{ font:inherit; padding:10px 12px; border-radius:8px; border:1px solid var(--line); background:#fff; color:var(--ink) }}
input:focus,select:focus {{ outline:none; border-color:var(--brand); box-shadow:0 0 0 3px #e8f0fd }}
button {{ background:var(--brand); color:#fff; border:0; cursor:pointer; font-weight:700 }}
button:hover {{ background:#0555c0 }} a {{ color:var(--brand) }}
</style></head><body>
<form method="post" action="/{"signup" if signup else "login"}">
<h1>{heading}</h1><p>{lead}</p>
<input type="hidden" name="next" value="{n}">
{fields}
<label>Email<input type="email" name="email" value="{v("email")}" autocomplete="email" {autofocus}required></label>
<label>Password<input type="password" name="password" {password_attrs} required></label>
<button type="submit">{button}</button>
<p class="err" role="alert">{escape(error)}</p>
<p>{other}</p>
</form></body></html>"""
