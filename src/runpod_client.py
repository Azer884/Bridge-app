"""RunPod serverless vLLM client. Credentials come from the environment only."""
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path


class RunPodError(RuntimeError):
    pass


def load_dotenv(path=".env"):
    p = Path(path)
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


class RunPodClient:
    def __init__(self, api_key, endpoint_id, timeout_s=300, sampling=None):
        self.api_key, self.endpoint_id, self.timeout_s = api_key, endpoint_id, timeout_s
        self.sampling = sampling or {"temperature": 0.2, "max_tokens": 400}

    @classmethod
    def from_env(cls, endpoint_var="RUNPOD_ENDPOINT_ID", key_var="RUNPOD_API_KEY", **kwargs):
        """key_var may name an endpoint-specific key; it falls back to RUNPOD_API_KEY."""
        load_dotenv()
        key = os.environ.get(key_var) or os.environ.get("RUNPOD_API_KEY")
        endpoint = os.environ.get(endpoint_var)
        if not key or not endpoint:
            raise RunPodError(f"{key_var} (or RUNPOD_API_KEY) and {endpoint_var} must be set")
        return cls(key, endpoint, **kwargs)

    def _call(self, url, payload=None):
        req = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            data=json.dumps(payload).encode() if payload is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as err:
            raise RunPodError(f"RunPod request failed: {err}") from err

    def health(self):
        """Job and worker counts for this endpoint (RunPod's /health)."""
        return self._call(f"https://api.runpod.ai/v2/{self.endpoint_id}/health")

    def chat(self, messages, sampling=None):
        """Return the assistant message text. runsync gives up after ~90s, so poll /status."""
        base = f"https://api.runpod.ai/v2/{self.endpoint_id}"
        start = time.time()
        body = self._call(f"{base}/runsync",
                          {"input": {"messages": messages, "sampling_params": sampling or self.sampling}})
        while body.get("status") in ("IN_QUEUE", "IN_PROGRESS"):
            if time.time() - start > self.timeout_s:
                raise RunPodError("RunPod job timed out (worker cold start?)")
            time.sleep(3)
            body = self._call(f"{base}/status/{body['id']}")
        if body.get("status") != "COMPLETED":
            raise RunPodError(f"RunPod job ended with status {body.get('status')}: {body.get('error')}")
        try:
            return body["output"][0]["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as err:
            raise RunPodError(f"unexpected RunPod output shape: {err}") from err
