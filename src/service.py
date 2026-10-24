"""One incoming event -> the replies to send. Channel-neutral: no HTTP, no WhatsApp here."""
import logging
import time
from dataclasses import asdict, replace

from .assessment import LOW_CONFIDENCE, combine, from_dict
from . import flow, persona as persona_module
from .assistant import PHOTO_CONDITION, handle_message
from .guard import clean_profile_name, clean_profile_phone
from .i18n import ISSUE_MS, STRINGS, t
from .pricing import PricingError, compute_quotation
from .quote_message import approved_quote_message, final_quote_message
from .schema import ask_for

PHOTO_REPLY = STRINGS["en"]["photo_reply"]
UNSUPPORTED_REPLY = STRINGS["en"]["unsupported"]
log = logging.getLogger("service")


def photo_summary(assessment, lang="en"):
    """Customer-facing line built only from the validated vocabulary, never from model text."""
    names = [ISSUE_MS.get(i, i) if lang == "ms" else i.replace("_", " ") for i in assessment.issues]
    issues = t("photo_issues", lang, issues=", ".join(names)) if names else ""
    text = t("photo_line", lang, level=t(f"level_{assessment.level}", lang), issues=issues)
    if assessment.level == "severe":
        text += t("photo_severe", lang)
    return text


class IncomingService:
    def __init__(self, store, config, client, handler=handle_message, photo_assessor=None, transcriber=None):
        """photo_assessor(media_id) -> ConditionAssessment or None; it may raise.
        transcriber(media_id) -> (text, language) for a voice note, or None; it may raise."""
        self.store, self.config, self.client, self.handler = store, config, client, handler
        self.photo_assessor, self.transcriber = photo_assessor, transcriber

    def _turn_config(self):
        """The business config plus the persona the dashboard has selected right now."""
        persona = persona_module.active(self.config, self.store)
        return {**self.config, "persona": persona} if persona else self.config

    def _price(self, state):
        photo = from_dict(state.photo_assessment) if state.photo_assessment else None
        try:
            quote = compute_quotation(state.verified, self.config["pricing"], photo)
        except PricingError:
            return None                     # the team prices it by hand
        if state.estimated:
            quote.assumptions.append("customer estimated, not measured: " + ", ".join(state.estimated)
                                     + " (the larger figure of any range was used)")
        quote.assumptions.append("an estimate from the customer's own dimensions: the team confirms the "
                                 "real price after measuring on site")
        return quote

    def _with_quote(self, state, reply):
        """When the job and contact details are complete, price once and keep the draft for the SME.
        The customer sees no number until the SME approves it. A size corrected afterwards re-prices the
        draft silently (until the SME has approved it)."""
        if "pricing" not in self.config or state.stage != "done":
            return reply
        if state.quote is not None:
            if state.quote_stale and state.quote_status in ("pending_approval", "needs_inspection"):
                quote = self._price(state)
                if quote is not None:
                    state.quote = quote.to_dict()
                    state.quote_status = "needs_inspection" if quote.status == "needs_inspection" else "pending_approval"
            state.quote_stale = False
            return reply
        quote = self._price(state)
        if quote is None:
            return reply
        state.quote = quote.to_dict()
        if quote.status == "needs_inspection":
            state.quote_status, state.needs_human = "needs_inspection", True
            owner = (self.config.get("owner") or {}).get("name") or ("pasukan kami" if state.lang == "ms" else "our team")
            # replaces the closing line, which promised a quotation the customer will not get yet
            return t("inspection_wrap", state.lang, owner=owner, message=t("inspection_message", state.lang))
        state.quote_status = "pending_approval"
        return reply

    # --- the SME's side -------------------------------------------------------------------------
    def quotes(self, status="pending_approval"):
        """The SME's view: drafts with their breakdown. Every quote is an estimate until the site visit."""
        return [{"user_id": s.conversation_id, "status": s.quote_status, "customer": s.channel, "lang": s.lang,
                 "job": s.verified, "quote": s.quote, "is_estimate": True, "estimated_fields": s.estimated,
                 "attention": s.attention, "followups": s.followups}
                for s in self.store.conversations() if s.quote and s.quote_status == status]

    def customers(self):
        """Every customer with all their jobs (earlier ones and the current one), for order tracking."""
        out = []
        for s in self.store.conversations():
            current = ({"verified": s.verified, "quote": s.quote, "quote_status": s.quote_status,
                        "estimated": s.estimated, "followups": s.followups, "created_at": s.created_at,
                        "open": s.stage != "done" or s.quote_status not in ("final",)}
                       if s.verified else None)
            out.append({"user_id": s.conversation_id, "name": s.verified.get("customer_name") or s.channel.get("name"),
                        "phone": s.verified.get("phone") or s.channel.get("phone"), "lang": s.lang,
                        "stage": s.stage, "attention": s.attention, "needs_human": s.needs_human,
                        "orders": s.orders + ([current] if current else [])})
        return out

    def approve_quote(self, user_id, send, total=None):
        """SME approval. Sends the customer the estimate only (never the breakdown); the quote is marked
        approved only if the send worked. Raises ValueError when nothing is waiting for approval."""
        with self.store.lock(user_id):
            state = self.store.load(user_id)
            if state.quote_status != "pending_approval":
                raise ValueError("no quote is waiting for approval")
            amount = state.quote["total"] if total is None else total
            message = approved_quote_message(amount, state.quote["currency"],
                                             self.config.get("business_name", "us"), state.lang)
            if not send(message):
                return False
            state.quote["approved_total"], state.quote_status = amount, "approved"
            state.waiting_count, state.attention = 0, False
            self.store.save(state)
            self.store.log_message(user_id, "out", message)
            return True

    def confirm_final(self, user_id, send, total):
        """After the team has measured on site: send the final price. Raises ValueError unless the
        estimate was approved first."""
        with self.store.lock(user_id):
            state = self.store.load(user_id)
            if state.quote_status != "approved":
                raise ValueError("the estimate must be approved before a final price is confirmed")
            message = final_quote_message(total, state.quote["currency"],
                                          self.config.get("business_name", "us"), state.lang)
            if not send(message):
                return False
            state.quote["final_total"], state.quote_status = total, "final"
            self.store.save(state)
            self.store.log_message(user_id, "out", message)
            return True

    # --- the customer's side -------------------------------------------------------------------
    def _photo_reply(self, state, media_id):
        assessment = None
        if self.photo_assessor and media_id:
            try:
                assessment = self.photo_assessor(media_id)
            except Exception:
                log.exception("photo assessment failed for media %s", media_id)
        if assessment is None or assessment.confidence < LOW_CONFIDENCE:
            return t("photo_reply", state.lang)
        previous = from_dict(state.photo_assessment) if state.photo_assessment else None
        state.photo_assessment = asdict(combine(previous, assessment))
        if state.stage == "job":
            state.verified.setdefault("surface_condition", PHOTO_CONDITION)   # the photo answers it
        return photo_summary(assessment, state.lang)

    def _voice_text(self, event):
        """The transcript of a voice note, or None with the reason: 'off' (no transcriber) or 'failed'."""
        if self.transcriber is None or not event.media_id:
            return None, "off"
        try:
            result = self.transcriber(event.media_id)
        except Exception:
            log.exception("voice note transcription failed for media %s", event.media_id)
            return None, "failed"
        text = (result[0] if result else "").strip()
        return (text, "") if text else (None, "failed")

    def handle(self, event):
        """Returns a list of reply strings (empty for a duplicate delivery)."""
        return self.handle_batch([event])

    def handle_batch(self, events):
        """Messages one customer sent in quick succession: text messages are read as one message, so
        "5" followed by "m" or two thoughts in a row get one coherent answer."""
        claimed = [e for e in events if self.store.claim_message(e.message_id, e.user_id)]
        if not claimed:
            return []
        merged = []
        for event in claimed:
            if merged and event.type == "text" and merged[-1].type == "text" and event.text.strip():
                merged[-1] = replace(merged[-1], text=merged[-1].text.rstrip() + "\n" + event.text.strip())
            else:
                merged.append(event)
        try:
            replies = []
            with self.store.lock(claimed[0].user_id):
                for event in merged:
                    replies += self._handle_locked(event)
            return replies
        except Exception:
            for event in claimed:
                self.store.release_message(event.message_id)
            raise

    def _handle_locked(self, event):
        state = self.store.load(event.user_id)
        if not state.history and not state.channel:
            channel = {"name": clean_profile_name(event.profile_name),
                       "phone": clean_profile_phone(event.phone or "+" + event.user_id)}
            state.channel = {k: v for k, v in channel.items() if v}
        if not state.created_at:
            state.created_at = time.time()

        if event.type == "text" and event.text.strip():
            self.store.log_message(event.user_id, "in", event.text)
            reply = self._with_quote(state, self.handler(state, event.text, self._turn_config(), self.client).reply)
        elif event.type == "audio":
            self.store.log_message(event.user_id, "in", "[voice note]", event.media_id)
            text, problem = self._voice_text(event)
            if text is None:
                reply = t("voice_off" if problem == "off" else "voice_fail", state.lang)
            else:
                self.store.log_message(event.user_id, "in", text)
                answer = self._with_quote(state, self.handler(state, text, self._turn_config(), self.client).reply)
                heard = t("heard", state.lang, text=text[:200])
                reply = f"{heard} {answer}".strip() if answer else ""
        elif event.type == "image":
            self.store.log_message(event.user_id, "in", event.text, event.media_id)
            reply = self._photo_reply(state, event.media_id)
            nxt = state.next_missing(self.config) if state.stage == "job" else None
            if nxt:
                reply += " " + ask_for(nxt, state)
            elif state.stage == "job" and state.service_checked and self._turn_config().get("persona"):
                reply += " " + flow.contact_intro(state)      # the photo answered the last open question
        elif event.type == "unsupported":
            self.store.log_message(event.user_id, "in", "[unsupported message type]")
            reply = t("unsupported", state.lang)
        else:
            return []

        self.store.save(state)
        if reply:
            self.store.log_message(event.user_id, "out", reply)
        return [reply] if reply else []
