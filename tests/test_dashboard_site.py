"""The hosted dashboard: password sign-in, cookie, gated /app, static files, and the API accepting the cookie."""
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from src import webauth
from src.server import create_app
from tests.test_dashboard_calendar import Sender, priced_service

ENV = {"INCOMING_API_KEY": "key", "SESSION_SECRET": "s3cret",
       "MESSAGE_WINDOW_SECONDS": "0"}
SIGNUP = ("name=Aisyah+Tan&business=Tan+Painting&trade=painting&email=aisyah%40example.com"
          "&password=open+sesame12")


class WebAuthTests(unittest.TestCase):
    def test_cookie_signature_expiry_and_tampering(self):
        secret = b"s3cret"
        cookie = webauth.make_cookie(secret)
        self.assertTrue(webauth.valid_cookie(secret, cookie))
        self.assertFalse(webauth.valid_cookie(b"other", cookie))
        self.assertFalse(webauth.valid_cookie(secret, cookie[:-1] + ("0" if cookie[-1] != "0" else "1")))
        self.assertFalse(webauth.valid_cookie(secret, "9999999999.abc"))
        self.assertFalse(webauth.valid_cookie(secret, webauth.make_cookie(secret, now=time.time() - 13 * 3600)))
        self.assertFalse(webauth.valid_cookie(secret, ""))
        named = webauth.make_cookie(secret, email="a@b.co")
        self.assertEqual(webauth.read_cookie(secret, named), (True, "a@b.co"))
        forged = named.replace(b"a@b.co".hex(), b"x@b.co".hex())
        self.assertEqual(webauth.read_cookie(secret, forged), (False, "x@b.co"))
        self.assertFalse(webauth.valid_cookie(b"", cookie))

    def test_next_must_stay_on_the_site(self):
        self.assertEqual(webauth.safe_next("/app/quotes"), "/app/quotes")
        for bad in ("https://evil.example", "//evil.example", "/\\evil.example", None, ""):
            self.assertEqual(webauth.safe_next(bad), "/app")

    def test_limiter_blocks_after_five_wrong_passwords(self):
        limiter = webauth.LoginLimiter()
        for _ in range(5):
            self.assertFalse(limiter.blocked("ip"))
            limiter.fail("ip")
        self.assertTrue(limiter.blocked("ip"))
        self.assertFalse(limiter.blocked("other"))
        self.assertFalse(limiter.blocked("ip", now=time.time() + 700))     # the window passes
        limiter.fail("ip")
        limiter.clear("ip")
        self.assertFalse(limiter.blocked("ip"))


class SiteTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        site = Path(self.dir.name)
        (site / "assets").mkdir()
        (site / "index.html").write_text("<html>dashboard shell</html>", encoding="utf-8")
        (site / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
        (site.parent / "secret.txt").write_text("outside the site", encoding="utf-8")
        self.service = priced_service()
        self.env = {**ENV, "DASHBOARD_DIR": str(site)}
        self.api = TestClient(create_app(self.service, Sender(), self.env), follow_redirects=False)

    def tearDown(self):
        self.dir.cleanup()

    FORM = {"content-type": "application/x-www-form-urlencoded"}

    def signup(self, body=SIGNUP, next="/app/quotes", api=None, headers=None):
        return (api or self.api).post("/signup", content=f"{body}&next={next}", headers={**self.FORM, **(headers or {})})

    def login(self, password="open sesame12", next="/app/quotes", api=None, headers=None):
        if not self.service.store.get_setting("accounts"):
            self.signup(api=api)
            (api or self.api).cookies.clear()
        return (api or self.api).post("/login", content=f"email=aisyah%40example.com&password={password}&next={next}".replace(" ", "+"),
                                      headers={**self.FORM, **(headers or {})})

    def test_the_root_is_the_sign_in_page_then_the_app(self):
        page = self.api.get("/")
        self.assertEqual(page.status_code, 200)                                      # the host's health check
        self.assertIn('name="next" value="/app"', page.text)
        self.login(next="/app")
        res = self.api.get("/")
        self.assertEqual((res.status_code, res.headers["location"]), (303, "/app"))

    def test_assets_are_public(self):
        asset = self.api.get("/assets/app.js")
        self.assertEqual(asset.text, "console.log(1)")
        self.assertIn("immutable", asset.headers["cache-control"])

    def test_app_needs_the_sign_in(self):
        res = self.api.get("/app/quotes/60123456789")
        self.assertEqual((res.status_code, res.headers["location"]), (303, "/login?next=/app/quotes/60123456789"))
        self.assertEqual(self.api.get("/app").status_code, 303)
        page = self.api.get("/login?next=/app/pipeline")
        self.assertIn('name="next" value="/app/pipeline"', page.text)

    def test_wrong_password_then_right_password(self):
        bad = self.login("nope")
        self.assertEqual(bad.status_code, 401)
        self.assertIn("not right", bad.text)
        self.assertNotIn("set-cookie", bad.headers)
        good = self.login()
        self.assertEqual((good.status_code, good.headers["location"]), (303, "/app/quotes"))
        cookie = good.headers["set-cookie"]
        self.assertIn("httponly", cookie.lower())
        self.assertIn("samesite=lax", cookie.lower())
        self.assertIn("dashboard shell", self.api.get("/app/quotes").text)           # the cookie rides along
        self.assertIn("dashboard shell", self.api.get("/app/anything/else").text)     # client-side routes

    def test_the_cookie_also_opens_the_api_and_the_key_still_works(self):
        self.assertEqual(self.api.get("/api/quotes").status_code, 401)
        self.assertEqual(self.api.get("/api/quotes", headers={"x-api-key": "key"}).status_code, 200)
        self.login()
        self.assertEqual(self.api.get("/api/quotes").status_code, 200)
        self.assertEqual(self.api.get("/api/pipeline").status_code, 200)
        self.api.cookies.clear()
        self.api.cookies.set(webauth.COOKIE, "123.forged")
        self.assertEqual(self.api.get("/api/quotes").status_code, 401)

    def test_secure_cookie_behind_https_proxy(self):
        res = self.login(headers={"x-forwarded-proto": "https"})
        self.assertIn("secure", res.headers["set-cookie"].lower())

    def test_open_redirect_is_refused(self):
        res = self.login(next="https://evil.example")
        self.assertEqual(res.headers["location"], "/app")

    def test_five_wrong_passwords_lock_the_address_out(self):
        for _ in range(5):
            self.assertEqual(self.login("nope").status_code, 401)
        self.assertEqual(self.login("nope").status_code, 429)
        self.assertEqual(self.login().status_code, 429)                              # even the right one, for now
        other = self.login(headers={"x-forwarded-for": "203.0.113.9"})
        self.assertEqual(other.status_code, 303)
        self.assertIn("login_failed", [e["kind"] for e in self.service.store.events(10)])

    def test_logout_clears_the_cookie(self):
        self.login()
        res = self.api.post("/logout")
        self.assertEqual(res.status_code, 303)
        self.assertEqual(self.api.get("/api/quotes").status_code, 401)

    def test_cannot_read_files_outside_the_site(self):
        for path in ("/../secret.txt", "/..%2fsecret.txt", "/assets/../../secret.txt"):
            self.assertNotIn("outside the site", self.api.get(path).text, path)

    def test_unknown_api_paths_are_json_404_not_the_dashboard(self):
        res = self.api.get("/api/nothing-here")
        self.assertEqual((res.status_code, res.json()), (404, {"detail": "Not Found"}))

    def test_sign_in_is_unavailable_until_a_secret_is_set(self):
        api = TestClient(create_app(self.service, Sender(), {**self.env, "SESSION_SECRET": "", "INCOMING_API_KEY": ""}),
                         follow_redirects=False)
        self.assertEqual(self.signup(api=api).status_code, 503)

    def test_signup_creates_an_account_signs_in_and_remembers_the_trade(self):
        page = self.api.get("/signup?next=/app/pipeline")
        self.assertIn('value="aircon"', page.text)
        self.assertIn('value="painting"', page.text)
        res = self.signup()
        self.assertEqual((res.status_code, res.headers["location"]), (303, "/app/quotes"))
        self.assertIn("dashboard shell", self.api.get("/app/quotes").text)
        me = self.api.get("/api/me").json()
        self.assertEqual((me["email"], me["business"], me["trade"]), ("aisyah@example.com", "Tan Painting", "painting"))
        self.assertNotIn("password", me)
        self.assertNotIn("open sesame12", self.service.store.get_setting("accounts"))      # only a hash is kept

    def test_both_trades_can_sign_up_and_use_the_same_api(self):
        self.signup(SIGNUP.replace("trade=painting", "trade=aircon"))
        self.assertEqual(self.api.get("/api/me").json()["trade"], "aircon")
        self.assertEqual(self.api.get("/api/quotes").status_code, 200)

    def test_signup_refuses_bad_input_and_a_second_account_with_the_same_email(self):
        for body, word in ((SIGNUP.replace("trade=painting", "trade=plumbing"), "trade"),
                           (SIGNUP.replace("open+sesame12", "short"), "password"),
                           (SIGNUP.replace("aisyah%40example.com", "nope"), "email"),
                           (SIGNUP.replace("name=Aisyah+Tan", "name="), "name")):
            res = self.signup(body)
            self.assertEqual(res.status_code, 400, word)
            self.assertIn(word, res.text.lower())
            self.assertNotIn("set-cookie", res.headers)
        self.assertEqual(self.signup().status_code, 303)
        again = self.signup()
        self.assertEqual(again.status_code, 400)
        self.assertIn("already has an account", again.text)

    def test_the_wrong_email_and_the_wrong_password_look_the_same(self):
        self.signup()
        wrong_pw = self.login("nope")
        wrong_email = self.api.post("/login", content="email=nobody%40example.com&password=open+sesame12", headers=self.FORM)
        self.assertEqual((wrong_pw.status_code, wrong_email.status_code), (401, 401))
        for res in (wrong_pw, wrong_email):
            self.assertIn("That email or password is not right.", res.text)

    def test_me_needs_a_session_that_names_an_account(self):
        self.assertEqual(self.api.get("/api/me").status_code, 401)
        self.api.cookies.set(webauth.COOKIE, webauth.make_cookie(b"s3cret"))                # signed in, but names nobody
        self.assertEqual(self.api.get("/api/me").status_code, 401)

    def test_without_a_built_dashboard_everything_stays_as_before(self):
        api = TestClient(create_app(self.service, Sender(), {**ENV, "DASHBOARD_DIR": "/nonexistent"}), follow_redirects=False)
        self.assertEqual(api.get("/").json(), {"ok": True})                         # the host's health check
        self.assertEqual(api.get("/health").json(), {"ok": True})
        self.assertEqual(api.get("/app/quotes").status_code, 404)


if __name__ == "__main__":
    unittest.main()
