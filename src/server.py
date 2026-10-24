"""HTTP front door.

  Customer path
    GET  /webhook          Meta verification handshake (direct WhatsApp Cloud API)
    POST /webhook          Meta messages, HMAC-verified, answered in the background
    POST /incoming         flat JSON from n8n or any other front door -> {"replies": [...]}
  GET  /api/events                        recent webhook, send and error events (x-api-key)
  GET  /api/storage                       which database is in use and its row counts (x-api-key)
  Dashboard (x-api-key; the contract is frontend/shared/api.ts)
    GET  /api/quotes/{id}                   one customer: job, quote, editable params, chat, photos, audit
    POST /api/quotes/{id}/recalculate       {"params": {...}} the engine's price for the form values (not saved)
    PUT  /api/quotes/{id}/params            save the owner's corrections (logged, draft re-priced)
    POST /api/quotes/{id}/pdf               the customer's estimate letter as base64 (no breakdown)
    POST /api/quotes/{id}/slots             {"busy": [...]} suggested start times, same-area jobs grouped
    GET  /api/pipeline, GET /api/audit      every job by stage, and the recent audit trail
    GET/POST /api/bookings, PATCH/DELETE /api/bookings/{id}   the calendar; an offer is sent to the customer
    GET  /api/media/{id}                    a customer photo fetched from WhatsApp
    GET/POST/DELETE /api/whatsapp/...       the linked number shown in the dashboard
  SME quotations (x-api-key; the dashboard will call these)
    GET  /api/quotes                        drafts waiting for approval, with the price breakdown
    POST /api/quotes/{user_id}/approve      optional {"total": n}; sends the customer the estimate only
    POST /api/quotes/{user_id}/final        {"total": n}; after the site visit, sends the final price
    GET  /api/customers                     every customer with all their jobs (earlier and current)
  Personas (x-api-key; the dashboard picks the character the assistant speaks as)
    GET  /api/personas                      all characters and the active one
    PUT  /api/personas/{id}                 create or edit a character
    POST /api/personas/active               {"id": ...} switch character; applies to the next message
  Model APIs (one per model in .env; for the team and n8n, all need the x-api-key header)
    POST /api/text/chat    RUNPOD_ENDPOINT_ID         chat model, raw messages in, text out
    POST /api/vision/assess RUNPOD_VISION_ENDPOINT_ID vision model, one photo in, validated assessment out
    GET  /api/models/health                           worker and job counts for each model
  GET  /health
  GET  /login, POST /login, POST /logout    the dashboard's password sign-in (DASHBOARD_PASSWORD), sets a cookie
  GET  /, /app/...                          the built dashboard from ./dashboard (/app/... needs the sign-in)

The model APIs are raw access to the models, so they are for internal use. Customer messages
must go through /incoming, which applies the assistant's rules, screening and validation.

Run: uvicorn src.server:create_app --factory --port 8000
"""
import base64
import binascii
import dataclasses
import hmac
import json
import logging
import os
import threading
import time
from urllib.parse import parse_qs, quote
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from pydantic import BaseModel, Field

from . import persona as persona_module
from . import views, webauth
from .pdf import estimate_pdf
from .events import calls_from_meta_payload, from_flat, from_meta_payload
from .runpod_client import RunPodClient, RunPodError, load_dotenv
from .service import IncomingService
from .store import make_store
from .transcribe import Transcriber
from .vision import VisionError, assess_image, suggest_colours
from .whatsapp import WhatsAppSender, valid_signature

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("server")


def worker_state(data):
    """A model's readiness for the dashboard. RunPod's own counts are summarised on purpose: the dashboard decides
    "waking up" or "problem" by looking for those words anywhere in the reply, and RunPod's raw keys
    ("initializing", "failed", "throttled") are there even when everything is fine."""
    workers, jobs = data.get("workers") or {}, data.get("jobs") or {}
    idle = int(workers.get("idle") or 0) + int(workers.get("ready") or 0)
    busy = int(workers.get("running") or 0)
    booting, queued = int(workers.get("initializing") or 0), int(jobs.get("inQueue") or 0)
    sick = int(workers.get("unhealthy") or 0)
    if idle or busy:
        state = "ready"
    elif booting or queued:
        state = "waking"                    # a worker is starting, or a job is waiting for one
    elif sick:
        state = "down"
    else:
        state = "asleep"                    # scaled to zero: the first message starts a worker (2 to 5 minutes)
    return {"state": state, "idle": idle, "busy": busy, "queued": queued}


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(max_length=4000)


class TextRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=20)
    max_tokens: int = Field(400, ge=1, le=600)
    temperature: float = Field(0.2, ge=0, le=1)


class VisionRequest(BaseModel):
    image_base64: str
    mime: Literal["image/jpeg", "image/png", "image/webp"]


class ActivePersona(BaseModel):
    id: str


class ParamsBody(BaseModel):
    params: dict


class SlotsBody(BaseModel):
    busy: list[dict] = []


class BookingIn(BaseModel):
    user_id: str
    customer: str = ""
    phone: str = ""
    address: str = ""
    start: str
    end: str


class BookingPatch(BaseModel):
    start: str | None = None
    end: str | None = None
    status: Literal["confirmed", "tentative", "cancelled"] | None = None


class LinkBody(BaseModel):
    number: str = Field(min_length=6, max_length=20)


class OwnerMessage(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class FinalRequest(BaseModel):
    total: float = Field(gt=0, le=1_000_000)


class ApproveRequest(BaseModel):
    total: float | None = Field(None, gt=0, le=1_000_000)   # the SME may override the computed total


def _same(a, b):
    return bool(a) and bool(b) and hmac.compare_digest(a.encode(), b.encode())


def create_app(service=None, sender=None, env=None, text_client=None, vision_client=None, transcriber=None,
               call_handler=None):
    if env is None:
        load_dotenv()
        env = dict(os.environ)
    if text_client is None and service is None:
        text_client = RunPodClient.from_env()
    if sender is None:
        sender = WhatsAppSender.from_env(env)
    clients = {"text": text_client, "vision": vision_client}

    def model_client(name):
        """The vision client is built on first use, so the server starts without vision credentials."""
        if clients[name] is None:
            try:
                clients[name] = RunPodClient.from_env(
                    "RUNPOD_VISION_ENDPOINT_ID", key_var="RUNPOD_VISION_API_KEY", timeout_s=420,
                    sampling={"temperature": 0.1, "max_tokens": 300})   # 420 s covers a cold start
            except RunPodError as err:
                raise HTTPException(503, str(err))
        return clients[name]

    def assess_photo(media_id):
        image, mime = sender.fetch_media(media_id)
        assessment, _ = assess_image(model_client("vision"), image, mime)
        return assessment

    def suggest_colour(media_id):
        image, mime = sender.fetch_media(media_id)
        return suggest_colours(model_client("vision"), image, mime)

    if transcriber is None:
        transcriber = Transcriber.from_env(env)

    def transcribe_voice(media_id):
        audio, mime = sender.fetch_media(media_id)
        return transcriber.transcribe(audio, mime)

    if transcriber and sender and str(env.get("STT_WARMUP", "1")).lower() not in ("0", "false", "no", "off"):
        threading.Thread(target=transcriber.warm_up, daemon=True, name="stt-warm-up").start()

    if service is None:
        config_path = env.get("BUSINESS_CONFIG") or ROOT / "config" / "business_config.example.json"
        service = IncomingService(make_store(env, ROOT / "data" / "bridge.db"),
                                  json.loads(Path(config_path).read_text(encoding="utf-8")), text_client,
                                  photo_assessor=assess_photo if sender else None,
                                  colour_assessor=suggest_colour if sender else None,
                                  transcriber=transcribe_voice if sender and transcriber else None)
    clients["text"] = clients["text"] or service.client

    session_secret = (env.get("SESSION_SECRET") or env.get("INCOMING_API_KEY") or "").encode()
    dashboard_password = env.get("DASHBOARD_PASSWORD") or ""
    site = Path(env.get("DASHBOARD_DIR") or ROOT / "dashboard")
    limiter = webauth.LoginLimiter()

    def has_session(request):
        return webauth.valid_cookie(session_secret, request.cookies.get(webauth.COOKIE))

    def require_key(request):
        if has_session(request):                # the web dashboard: signed in with the password
            return
        if not env.get("INCOMING_API_KEY"):
            raise HTTPException(503, "INCOMING_API_KEY is not configured")
        if not _same(request.headers.get("x-api-key"), env["INCOMING_API_KEY"]):
            raise HTTPException(401, "bad API key")

    def call_model(fn):
        try:
            return fn()
        except RunPodError as err:
            log.error("model call failed: %s", err)
            raise HTTPException(502, "model unavailable")

    app = FastAPI(title="Painting assistant")
    if call_handler is None:
        from .whatsapp_calling import handle_call_event      # LiveKit is only imported when a call arrives
        call_handler = handle_call_event
    origins = [o.strip() for o in (env.get("CORS_ORIGINS") or "").split(",") if o.strip()]
    if origins:                                 # the web dashboard on another origin; native apps need none
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])

    def notifier(user_id):
        """send(text) to the customer; a missing sender just reports failure."""
        return (lambda text: sender.send_text(user_id, text)) if sender else (lambda text: False)

    window = float(env.get("MESSAGE_WINDOW_SECONDS") or 2.0)    # messages this close together are read as one
    inbox, running, inbox_lock = {}, set(), threading.Lock()

    def deliver(user_id, events):
        try:
            replies = service.handle_batch(events)
        except Exception as err:
            log.exception("failed to handle messages %s", [e.message_id for e in events])
            service.store.log_event("handler_error", f"{user_id}: {type(err).__name__}: {err}")
            return
        for reply in replies:
            if sender is None:
                service.store.log_event("no_sender", "WHATSAPP_TOKEN or WHATSAPP_PHONE_NUMBER_ID is not set")
            elif sender.send_text(user_id, reply):
                service.store.log_event("sent", user_id)
            else:
                service.store.log_event("send_failed", f"{user_id}: {getattr(sender, 'last_error', '')}")

    def process_and_send(event):
        """Collect the customer's messages for a short window, then answer them together. One worker per
        customer: a message arriving while it runs is picked up on its next round."""
        with inbox_lock:
            inbox.setdefault(event.user_id, []).append(event)
            if event.user_id in running:
                return
            running.add(event.user_id)
        try:
            while True:
                time.sleep(window)
                with inbox_lock:
                    batch = inbox.pop(event.user_id, [])
                    if not batch:
                        running.discard(event.user_id)
                        return
                deliver(event.user_id, batch)
        except BaseException:
            with inbox_lock:
                running.discard(event.user_id)
            raise

    def process_call(call):
        """A WhatsApp call event: connect hands the call to the voice agent, terminate hangs it up. Off unless
        WHATSAPP_CALLING_ENABLED=true, and each event is handled once."""
        key = f"{call['id']}:{call['event']}"
        if not service.store.claim_call_event(key):
            return
        flag = str(env.get("WHATSAPP_CALLING_ENABLED") or "").lower()
        keys = ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")
        # Calls switch themselves on once LiveKit is configured; WHATSAPP_CALLING_ENABLED=false keeps them off.
        if flag == "false" or (flag != "true" and not all(env.get(k) for k in keys)):
            missing = [k for k in keys if not env.get(k)]
            service.store.log_event("call_ignored", "calling is off by WHATSAPP_CALLING_ENABLED=false" if flag == "false"
                                    else "calling is off: LiveKit secrets missing (" + ", ".join(missing) + ")")
            return
        try:
            call_handler(call, env)
            service.store.log_event("call_handled", f"{call['event']} {call['id']}")
        except Exception as err:
            service.store.release_call_event(key)            # Meta's retry may succeed
            log.exception("failed to handle WhatsApp call event")
            service.store.log_event("call_error", f"{call['event']} {type(err).__name__}: {str(err)[:200]}")

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/", include_in_schema=False)
    def home():
        """The landing page when the dashboard is built; otherwise a plain 200 for the host's health check."""
        if (site / "index.html").is_file():
            return FileResponse(site / "index.html", headers={"Cache-Control": "no-cache"})
        return {"ok": True}

    @app.get("/webhook")
    def verify(mode: str = Query(None, alias="hub.mode"), token: str = Query(None, alias="hub.verify_token"),
               challenge: str = Query("", alias="hub.challenge")):
        if mode == "subscribe" and _same(token, env.get("WHATSAPP_VERIFY_TOKEN")):
            return PlainTextResponse(challenge)
        raise HTTPException(403, "verification failed")

    @app.post("/webhook")
    async def webhook(request: Request, background: BackgroundTasks):
        if not env.get("WHATSAPP_APP_SECRET"):
            raise HTTPException(503, "WHATSAPP_APP_SECRET is not configured")
        raw = await request.body()
        if not valid_signature(raw, request.headers.get("x-hub-signature-256"), env["WHATSAPP_APP_SECRET"]):
            service.store.log_event("webhook_bad_signature", "check WHATSAPP_APP_SECRET against the Meta app secret")
            raise HTTPException(403, "bad signature")
        try:
            payload = json.loads(raw)
        except ValueError:
            raise HTTPException(400, "invalid JSON")
        events, calls = from_meta_payload(payload), calls_from_meta_payload(payload)
        service.store.log_event("webhook", f"{len(events)} message(s): " + ", ".join(e.type for e in events)
                                + (f"; {len(calls)} call event(s)" if calls else ""))
        for event in events:
            background.add_task(process_and_send, event)
        for call in calls:
            background.add_task(process_call, call)
        return {"ok": True}                     # answer fast: Meta retries slow webhooks

    @app.post("/incoming")
    def incoming(body: dict, request: Request):
        require_key(request)
        try:
            event = from_flat(body)
        except ValueError as err:
            raise HTTPException(422, str(err))
        replies = service.handle(event)
        return {"replies": replies, "lang": service.store.load(event.user_id).lang}   # the voice agent speaks in it

    @app.post("/api/text/chat")
    def text_chat(body: TextRequest, request: Request):
        require_key(request)
        sampling = {"temperature": body.temperature, "max_tokens": body.max_tokens}
        text = call_model(lambda: model_client("text").chat([m.model_dump() for m in body.messages], sampling))
        return {"text": text}

    @app.post("/api/vision/assess")
    def vision_assess(body: VisionRequest, request: Request):
        require_key(request)
        try:
            image = base64.b64decode(body.image_base64, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(422, "image_base64 is not valid base64")
        client = model_client("vision")
        try:
            assessment, _ = call_model(lambda: assess_image(client, image, body.mime))
        except VisionError as err:
            raise HTTPException(422, str(err))
        if assessment is None:
            raise HTTPException(502, "vision model returned no usable assessment")
        return dataclasses.asdict(assessment)

    @app.get("/api/voice/health")
    def voice_health(request: Request):
        """Is voice-note transcription on, is the model loaded, and why did the last attempt fail."""
        require_key(request)
        if transcriber is None:
            return {"enabled": False, "loaded": False, "error": "STT_ENABLED is off"}
        return {"enabled": True, "model": transcriber.model_size, "loaded": transcriber.loaded,
                "error": transcriber.last_error}

    @app.get("/api/storage")
    def storage(request: Request):
        require_key(request)
        return service.store.stats()

    @app.get("/api/events")
    def recent_events(request: Request, limit: int = Query(50, ge=1, le=200)):
        require_key(request)
        return {"events": [{**e, "ts": views._iso(e["ts"]), "ok": not any(w in e["kind"] for w in ("fail", "error"))}
                           for e in service.store.events(limit)]}

    @app.get("/api/quotes")
    def list_quotes(request: Request, status: str = "pending_approval"):
        require_key(request)
        return {"quotes": service.quotes(status)}

    @app.post("/api/quotes/{user_id}/approve")
    def approve_quote(user_id: str, request: Request, body: ApproveRequest = None):
        require_key(request)
        if sender is None:
            raise HTTPException(503, "WhatsApp sender is not configured")
        try:
            sent = service.approve_quote(user_id, lambda text: sender.send_text(user_id, text),
                                         body.total if body else None)
        except ValueError as err:
            raise HTTPException(409, str(err))
        if not sent:
            raise HTTPException(502, "could not send the quotation to the customer")
        return {"approved": True, "slots": service.slots(user_id)[:3]}      # the best times to offer next

    @app.get("/api/quotes/{user_id}")
    def quote_detail(user_id: str, request: Request):
        require_key(request)
        try:
            return service.detail(user_id)
        except KeyError:
            raise HTTPException(404, "no such customer")

    @app.post("/api/quotes/{user_id}/recalculate")
    def recalculate(user_id: str, body: ParamsBody, request: Request):
        require_key(request)
        try:
            return service.recalculate(user_id, body.params)
        except ValueError as err:
            raise HTTPException(409, str(err))

    @app.put("/api/quotes/{user_id}/params")
    def save_params(user_id: str, body: ParamsBody, request: Request):
        require_key(request)
        try:
            return service.save_params(user_id, body.params)
        except ValueError as err:
            raise HTTPException(409, str(err))

    @app.post("/api/quotes/{user_id}/pdf")
    def quote_pdf(user_id: str, body: ParamsBody, request: Request):
        """The customer's estimate letter (total and time only, no breakdown) for the form's current values."""
        require_key(request)
        try:
            state = service.store.load(user_id)
            quote = service.recalculate(user_id, body.params)["quote"]
        except ValueError as err:
            raise HTTPException(409, str(err))
        data = estimate_pdf(service.config.get("business_name", ""), views.customer_name(state), views.job_view(state), quote)
        return {"base64": base64.b64encode(data).decode(), "filename": f"estimate-{user_id}.pdf",
                "generated_at": datetime.now(timezone.utc).isoformat()}

    @app.post("/api/quotes/{user_id}/slots")
    def quote_slots(user_id: str, body: SlotsBody, request: Request):
        """Suggested start times: earliest free, and next to jobs in the same area to save travel."""
        require_key(request)
        return {"slots": service.slots(user_id, body.busy)}

    @app.get("/api/pipeline")
    def pipeline(request: Request):
        require_key(request)
        return {"quotes": service.pipeline()}

    @app.get("/api/audit")
    def audit(request: Request, limit: int = Query(20, ge=1, le=200)):
        require_key(request)
        return {"entries": service.audit_feed(limit)}

    @app.get("/api/bookings")
    def bookings(request: Request, from_: str = Query(None, alias="from"), to: str = None):
        require_key(request)
        return {"bookings": service.booking_list(from_, to)}

    @app.post("/api/bookings")
    def create_booking(body: BookingIn, request: Request):
        require_key(request)
        try:
            booking, notified = service.create_booking(body.user_id, body.start, body.end, notifier(body.user_id))
        except ValueError as err:
            raise HTTPException(409, str(err))
        return {**booking, "notified": notified}

    @app.patch("/api/bookings/{booking_id}")
    def patch_booking(booking_id: str, body: BookingPatch, request: Request):
        require_key(request)
        existing = service.store.get_booking(booking_id)
        if existing is None:
            raise HTTPException(404, "no such booking")
        try:
            return service.update_booking(booking_id, body.model_dump(exclude_none=True), notifier(existing["user_id"]))
        except ValueError as err:
            raise HTTPException(409, str(err))

    @app.delete("/api/bookings/{booking_id}", status_code=204)
    def remove_booking(booking_id: str, request: Request):
        require_key(request)
        existing = service.store.get_booking(booking_id)
        if existing is None:
            raise HTTPException(404, "no such booking")
        service.delete_booking(booking_id, notifier(existing["user_id"]))
        return Response(status_code=204)

    @app.get("/api/media/{media_id}")
    def media(media_id: str, request: Request):
        """A photo the customer sent, fetched from WhatsApp for the dashboard."""
        require_key(request)
        if sender is None:
            raise HTTPException(503, "WhatsApp sender is not configured")
        try:
            data, mime = sender.fetch_media(media_id)
        except Exception:
            raise HTTPException(404, "photo not available")
        return Response(content=data, media_type=mime or "application/octet-stream")

    @app.get("/api/whatsapp/status")
    def whatsapp_status(request: Request):
        require_key(request)
        number = service.store.get_setting("whatsapp_number")
        return {"number": number, "status": "linked" if sender else ("pending" if number else "unlinked")}

    @app.post("/api/whatsapp/link")
    def whatsapp_link(body: LinkBody, request: Request):
        """Records the number shown in the dashboard. The real link is the WHATSAPP_* secrets on the server."""
        require_key(request)
        service.store.set_setting("whatsapp_number", body.number)
        return {"number": body.number, "status": "linked" if sender else "pending"}

    @app.delete("/api/whatsapp/link", status_code=204)
    def whatsapp_unlink(request: Request):
        require_key(request)
        service.store.set_setting("whatsapp_number", None)
        return Response(status_code=204)

    @app.post("/api/quotes/{user_id}/message")
    def owner_message(user_id: str, body: OwnerMessage, request: Request):
        """The owner writes to the customer in the assistant's place. The assistant then stays quiet for 30 minutes."""
        require_key(request)
        if sender is None:
            raise HTTPException(503, "WhatsApp sender is not configured")
        try:
            sent = service.send_owner_message(user_id, body.text, notifier(user_id))
        except KeyError:
            raise HTTPException(404, "no such customer")
        except ValueError as err:
            raise HTTPException(422, str(err))
        if not sent:
            raise HTTPException(502, "could not send the message to the customer")
        return {"sent": True}

    @app.post("/api/quotes/{user_id}/resume")
    def resume_assistant(user_id: str, request: Request):
        require_key(request)
        service.resume_assistant(user_id)
        return {"resumed": True}

    @app.post("/api/quotes/{user_id}/final")
    def final_price(user_id: str, body: FinalRequest, request: Request):
        require_key(request)
        if sender is None:
            raise HTTPException(503, "WhatsApp sender is not configured")
        try:
            sent = service.confirm_final(user_id, lambda text: sender.send_text(user_id, text), body.total)
        except ValueError as err:
            raise HTTPException(409, str(err))
        if not sent:
            raise HTTPException(502, "could not send the final price to the customer")
        return {"final": True}

    @app.get("/api/customers")
    def customers(request: Request):
        require_key(request)
        return {"customers": service.customers()}

    @app.get("/api/personas")
    def list_personas(request: Request):
        require_key(request)
        return {"personas": persona_module.all_personas(service.config, service.store),
                "active": persona_module.active_id(service.config, service.store)}

    @app.put("/api/personas/{persona_id}")
    def save_persona(persona_id: str, body: dict, request: Request):
        require_key(request)
        if not persona_module.ID_PATTERN.match(persona_id):
            raise HTTPException(422, "persona id must be 1 to 32 characters of a-z, 0-9, _ or -")
        try:
            persona = persona_module.clean(body)
        except ValueError as err:
            raise HTTPException(422, str(err))
        saved = service.store.get_setting("personas") or {}
        service.store.set_setting("personas", {**saved, persona_id: persona})
        return {"saved": persona_id}

    @app.post("/api/personas/active")
    def choose_persona(body: ActivePersona, request: Request):
        require_key(request)
        if body.id not in persona_module.all_personas(service.config, service.store):
            raise HTTPException(404, "unknown persona")
        service.store.set_setting("active_persona", body.id)
        return {"active": body.id}

    @app.get("/api/models/health")
    def models_health(request: Request):
        require_key(request)
        report = {}
        for name in ("text", "vision"):
            try:
                report[name] = worker_state(call_model(model_client(name).health))
            except HTTPException as err:
                report[name] = {"error": err.detail}
        return report

    # --- the hosted dashboard: login, the built frontend, and its client-side routes -----------------
    def client_id(request):
        forwarded = request.headers.get("x-forwarded-for", "")
        return forwarded.split(",")[0].strip() or (request.client.host if request.client else "?")

    @app.get("/login")
    def login_form(next: str = "/app"):
        return HTMLResponse(webauth.login_page(webauth.safe_next(next), enabled=bool(dashboard_password)))

    @app.post("/login")
    async def login(request: Request):
        form = {k: v[0] for k, v in parse_qs((await request.body()).decode("utf-8", "replace")).items()}
        target = webauth.safe_next(form.get("next"))
        who = client_id(request)
        if not dashboard_password or not session_secret:
            return HTMLResponse(webauth.login_page(target, enabled=False), status_code=503)
        if limiter.blocked(who):
            return HTMLResponse(webauth.login_page(target, "Too many wrong passwords. Try again in ten minutes."),
                                status_code=429)
        if not _same(form.get("password", ""), dashboard_password):
            limiter.fail(who)
            service.store.log_event("login_failed", who)
            return HTMLResponse(webauth.login_page(target, "That password is not right."), status_code=401)
        limiter.clear(who)
        response = RedirectResponse(target, status_code=303)
        secure = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
        response.set_cookie(webauth.COOKIE, webauth.make_cookie(session_secret), max_age=webauth.MAX_AGE,
                            httponly=True, samesite="lax", secure=secure)
        return response

    @app.post("/logout")
    def logout():
        response = RedirectResponse("/", status_code=303)
        response.delete_cookie(webauth.COOKIE)
        return response

    @app.get("/{path:path}")
    def dashboard_site(path: str, request: Request):
        if path.startswith("api/") or not (site / "index.html").is_file():
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        if (path == "app" or path.startswith("app/")) and not has_session(request):
            return RedirectResponse("/login?next=" + quote("/" + path, safe="/"), status_code=303)
        target = (site / path).resolve()
        if path and target.is_file() and site.resolve() in target.parents:
            immutable = path.startswith("assets/")
            return FileResponse(target, headers={"Cache-Control": "public, max-age=31536000, immutable" if immutable
                                                 else "no-cache"})
        return FileResponse(site / "index.html", headers={"Cache-Control": "no-cache"})     # client-side routes

    return app
