"""HTTP front door.

  Customer path
    GET  /webhook          Meta verification handshake (direct WhatsApp Cloud API)
    POST /webhook          Meta messages, HMAC-verified, answered in the background
    POST /incoming         flat JSON from n8n or any other front door -> {"replies": [...]}
  SME quotations (x-api-key; the dashboard will call these)
    GET  /api/quotes                        drafts waiting for approval, with the price breakdown
    POST /api/quotes/{user_id}/approve      optional {"total": n}; sends the customer the total only
  Personas (x-api-key; the dashboard picks the character the assistant speaks as)
    GET  /api/personas                      all characters and the active one
    PUT  /api/personas/{id}                 create or edit a character
    POST /api/personas/active               {"id": ...} switch character; applies to the next message
  Model APIs (one per model in .env; for the team and n8n, all need the x-api-key header)
    POST /api/text/chat    RUNPOD_ENDPOINT_ID         chat model, raw messages in, text out
    POST /api/vision/assess RUNPOD_VISION_ENDPOINT_ID vision model, one photo in, validated assessment out
    GET  /api/models/health                           worker and job counts for each model
  GET  /health

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
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from . import persona as persona_module
from .events import from_flat, from_meta_payload
from .runpod_client import RunPodClient, RunPodError, load_dotenv
from .service import IncomingService
from .store import SqliteStore
from .vision import VisionError, assess_image
from .whatsapp import WhatsAppSender, valid_signature

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("server")


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


class ApproveRequest(BaseModel):
    total: float | None = Field(None, gt=0, le=1_000_000)   # the SME may override the computed total


def _same(a, b):
    return bool(a) and bool(b) and hmac.compare_digest(a.encode(), b.encode())


def create_app(service=None, sender=None, env=None, text_client=None, vision_client=None):
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

    if service is None:
        config_path = env.get("BUSINESS_CONFIG") or ROOT / "config" / "business_config.example.json"
        service = IncomingService(SqliteStore(env.get("DATABASE_PATH") or ROOT / "data" / "bridge.db"),
                                  json.loads(Path(config_path).read_text(encoding="utf-8")), text_client,
                                  photo_assessor=assess_photo if sender else None)
    clients["text"] = clients["text"] or service.client

    def require_key(request):
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

    def process_and_send(event):
        try:
            replies = service.handle(event)
        except Exception:
            log.exception("failed to handle message %s", event.message_id)
            return
        for reply in replies:
            if sender is not None:
                sender.send_text(event.user_id, reply)

    @app.get("/health")
    def health():
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
            raise HTTPException(403, "bad signature")
        try:
            payload = json.loads(raw)
        except ValueError:
            raise HTTPException(400, "invalid JSON")
        for event in from_meta_payload(payload):
            background.add_task(process_and_send, event)
        return {"ok": True}                     # answer fast: Meta retries slow webhooks

    @app.post("/incoming")
    def incoming(body: dict, request: Request):
        require_key(request)
        try:
            event = from_flat(body)
        except ValueError as err:
            raise HTTPException(422, str(err))
        return {"replies": service.handle(event)}

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
        return {"approved": True}

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
                data = call_model(model_client(name).health)
                report[name] = {"jobs": data.get("jobs"), "workers": data.get("workers")}
            except HTTPException as err:
                report[name] = {"error": err.detail}
        return report

    return app
