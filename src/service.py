"""One incoming event -> the replies to send. Channel-neutral: no HTTP, no WhatsApp here."""
import logging
from dataclasses import asdict

from .assessment import LOW_CONFIDENCE, combine, from_dict
from .assistant import handle_message
from .guard import clean_profile_name, clean_profile_phone
from .pricing import PricingError, compute_quotation
from .quote_message import INSPECTION_MESSAGE, approved_quote_message
from .schema import FIELDS

PHOTO_REPLY = "Thanks, I've passed your photo to our team to look at."
UNSUPPORTED_REPLY = "Sorry, I can only read text messages and photos at the moment."
LEVEL_PHRASE = {"good": "in good condition", "minor": "in fairly good condition with minor wear",
                "moderate": "showing moderate wear or damage", "severe": "in poor condition"}
log = logging.getLogger("service")


def photo_summary(assessment):
    """Customer-facing line built only from the validated vocabulary, never from model text."""
    issues = ", ".join(i.replace("_", " ") for i in assessment.issues)
    text = f"Thanks for the photo. It looks like the surface is {LEVEL_PHRASE[assessment.level]}"
    text += f" (I can see: {issues})." if issues else "."
    text += " Our team will confirm this when they review your quote."
    if assessment.level == "severe":
        text += " Damage like this may need an inspection first."
    return text


class IncomingService:
    def __init__(self, store, config, client, handler=handle_message, photo_assessor=None):
        """photo_assessor(media_id) -> ConditionAssessment or None; it may raise."""
        self.store, self.config, self.client, self.handler = store, config, client, handler
        self.photo_assessor = photo_assessor

    def _with_quote(self, state, reply):
        """When the job and contact details are complete, price once and keep the draft for the SME.
        The customer sees no number until the SME approves it."""
        if state.stage != "done" or state.quote is not None or "pricing" not in self.config:
            return reply
        photo = from_dict(state.photo_assessment) if state.photo_assessment else None
        try:
            quote = compute_quotation(state.verified, self.config["pricing"], photo)
        except PricingError:
            return reply                    # the team prices it by hand
        state.quote = quote.to_dict()
        if quote.status == "needs_inspection":
            state.quote_status, state.needs_human = "needs_inspection", True
            return f"{reply}\n\n{INSPECTION_MESSAGE}"
        state.quote_status = "pending_approval"
        return reply

    def quotes(self, status="pending_approval"):
        """The SME's view: drafts with their breakdown."""
        return [{"user_id": s.conversation_id, "status": s.quote_status, "customer": s.channel,
                 "job": s.verified, "quote": s.quote}
                for s in self.store.conversations() if s.quote and s.quote_status == status]

    def approve_quote(self, user_id, send, total=None):
        """SME approval. Sends the customer the total only (never the breakdown); the quote is marked
        approved only if the send worked. Raises ValueError when nothing is waiting for approval."""
        with self.store.lock(user_id):
            state = self.store.load(user_id)
            if state.quote_status != "pending_approval":
                raise ValueError("no quote is waiting for approval")
            amount = state.quote["total"] if total is None else total
            message = approved_quote_message(amount, state.quote["currency"],
                                             self.config.get("business_name", "us"))
            if not send(message):
                return False
            state.quote["approved_total"], state.quote_status = amount, "approved"
            self.store.save(state)
            self.store.log_message(user_id, "out", message)
            return True

    def _photo_reply(self, state, media_id):
        assessment = None
        if self.photo_assessor and media_id:
            try:
                assessment = self.photo_assessor(media_id)
            except Exception:
                log.exception("photo assessment failed for media %s", media_id)
        if assessment is None or assessment.confidence < LOW_CONFIDENCE:
            return PHOTO_REPLY
        previous = from_dict(state.photo_assessment) if state.photo_assessment else None
        state.photo_assessment = asdict(combine(previous, assessment))
        return photo_summary(assessment)

    def handle(self, event):
        """Returns a list of reply strings (empty for a duplicate delivery)."""
        if not self.store.claim_message(event.message_id, event.user_id):
            return []
        try:
            with self.store.lock(event.user_id):
                return self._handle_locked(event)
        except Exception:
            self.store.release_message(event.message_id)
            raise

    def _handle_locked(self, event):
        state = self.store.load(event.user_id)
        if not state.history and not state.channel:
            channel = {"name": clean_profile_name(event.profile_name),
                       "phone": clean_profile_phone(event.phone or "+" + event.user_id)}
            state.channel = {k: v for k, v in channel.items() if v}

        if event.type == "text" and event.text.strip():
            self.store.log_message(event.user_id, "in", event.text)
            reply = self._with_quote(state, self.handler(state, event.text, self.config, self.client).reply)
        elif event.type == "image":
            self.store.log_message(event.user_id, "in", event.text, event.media_id)
            reply = self._photo_reply(state, event.media_id)
            nxt =state.next_missing(self.config) if state.stage == "job" else None
            if nxt:
                reply += " " + FIELDS[nxt].ask
        elif event.type == "unsupported":
            self.store.log_message(event.user_id, "in", "[unsupported message type]")
            reply = UNSUPPORTED_REPLY
        else:
            return []

        self.store.save(state)
        if reply:
            self.store.log_message(event.user_id, "out", reply)
        return [reply] if reply else []
