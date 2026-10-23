"""WhatsApp Cloud API helpers: signature check and text sender. Secrets come from the environment."""
import hashlib
import hmac
import json
import logging
import urllib.error
import urllib.request

GRAPH_VERSION = "v21.0"
MAX_TEXT = 4096
log = logging.getLogger("whatsapp")


def valid_signature(raw_body, header, app_secret):
    """X-Hub-Signature-256 is 'sha256=' + HMAC-SHA256(app_secret, raw body)."""
    if not app_secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[len("sha256="):])


class WhatsAppSender:
    def __init__(self, token, phone_number_id):
        self.token, self.phone_number_id = token, phone_number_id

    @classmethod
    def from_env(cls, env):
        token, number = env.get("WHATSAPP_TOKEN"), env.get("WHATSAPP_PHONE_NUMBER_ID")
        return cls(token, number) if token and number else None

    def send_text(self, to, text):
        """Returns True on success. Failures are logged, never raised: a failed send must not
        make the webhook fail and trigger duplicate deliveries."""
        body = {"messaging_product": "whatsapp", "to": to, "type": "text",
                "text": {"body": text[:MAX_TEXT]}}
        req = urllib.request.Request(
            f"https://graph.facebook.com/{GRAPH_VERSION}/{self.phone_number_id}/messages",
            data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20):
                return True
        except urllib.error.HTTPError as err:
            # Graph puts the real reason (expired token, bad number id, recipient not allowed) in the body
            log.error("WhatsApp send failed: HTTP %s %s", err.code, err.read()[:500].decode("utf-8", "replace"))
            return False
        except (urllib.error.URLError, TimeoutError) as err:
            log.error("WhatsApp send failed: %s", err)
            return False
