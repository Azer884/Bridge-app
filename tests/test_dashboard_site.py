"""The hosted dashboard: password sign-in, cookie, gated /app, static files, and the API accepting the cookie."""
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from src import webauth
from src.server import create_app
from tests.test_dashboard_calendar import Sender, priced_service

ENV = {"INCOMING_API_KEY": "key", "SESSION_SECRET": "s3cret", "DASHBOARD_PASSWORD": "open sesame",
       "MESSAGE_WINDOW_SECONDS": "0"}


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

    def login(self, password="open sesame", next="/app/quotes", api=None):
        return (api or self.api).post("/login", content=f"password={password}&next={next}".replace(" ", "+"),
                                      headers={"content-type": "application/x-www-form-urlencoded"})

    def test_landing_and_assets_are_public(self):
        self.assertIn("dashboard shell", self.api.get("/").text)
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
        self.api.cookies.set(webauth.COOKIE, "123.forged")
        self.assertEqual(self.api.get("/api/quotes").status_code, 401)

    def test_secure_cookie_behind_https_proxy(self):
        res = self.api.post("/login", content="password=open+sesame", headers={
            "content-type": "application/x-www-form-urlencoded", "x-forwarded-proto": "https"})
        self.assertIn("secure", res.headers["set-cookie"].lower())

    def test_open_redirect_is_refused(self):
        res = self.login(next="https://evil.example")
        self.assertEqual(res.headers["location"], "/app")

    def test_five_wrong_passwords_lock_the_address_out(self):
        for _ in range(5):
            self.assertEqual(self.login("nope").status_code, 401)
        self.assertEqual(self.login("nope").status_code, 429)
        self.assertEqual(self.login().status_code, 429)                              # even the right one, for now
        other = self.api.post("/login", content="password=open+sesame", headers={
            "content-type": "application/x-www-form-urlencoded", "x-forwarded-for": "203.0.113.9"})
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

    def test_login_is_unavailable_until_a_password_is_set(self):
        api = TestClient(create_app(self.service, Sender(), {**self.env, "DASHBOARD_PASSWORD": ""}), follow_redirects=False)
        self.assertEqual(self.login(api=api).status_code, 503)
        self.assertIn("DASHBOARD_PASSWORD", api.get("/login").text)

    def test_without_a_built_dashboard_everything_stays_as_before(self):
        api = TestClient(create_app(self.service, Sender(), {**ENV, "DASHBOARD_DIR": "/nonexistent"}), follow_redirects=False)
        self.assertEqual(api.get("/").json(), {"ok": True})                         # the host's health check
        self.assertEqual(api.get("/health").json(), {"ok": True})
        self.assertEqual(api.get("/app/quotes").status_code, 404)


if __name__ == "__main__":
    unittest.main()
