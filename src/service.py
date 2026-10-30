"""One incoming event -> the replies to send. Channel-neutral: no HTTP, no WhatsApp here."""
import logging
import re
import time
from dataclasses import asdict, replace
from datetime import datetime

from .assessment import LOW_CONFIDENCE, combine, from_dict
from . import consent, contact, flow, persona as persona_module, scheduling, views
from .assistant import PHOTO_CONDITION, advance, handle_message
from .guard import clean_profile_name, clean_profile_phone
from .i18n import COLOUR_MS, ISSUE_MS, STRINGS, detect, t
from .pricing import PricingError, compute_quotation
from .quote_message import approved_quote_message, duration_text, final_quote_message
from .schema import ask_for

PHOTO_REPLY = STRINGS["en"]["photo_reply"]
_PHOTO_SENT = re.compile(r"\b(already|just|i('ve| have)?|i)\s+sent\b|\bsent (it|the (photo|picture|image|pic))\b|"
                         r"\b(dah|sudah|telah) hantar\b", re.I)
UNSUPPORTED_REPLY = STRINGS["en"]["unsupported"]
LEGACY_STATUS = {"final": "completed"}
TAKEOVER_SECONDS = 1800        # how long the assistant stays quiet after the owner replies by hand
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
    def __init__(self, store, config, client, handler=handle_message, photo_assessor=None, transcriber=None,
                 colour_assessor=None, notify=None):
        """photo_assessor(media_id) -> ConditionAssessment or None; it may raise.
        transcriber(media_id) -> (text, language) for a voice note, or None; it may raise."""
        self.store, self.config, self.client, self.handler = store, config, client, handler
        self.photo_assessor, self.transcriber = photo_assessor, transcriber
        self.colour_assessor = colour_assessor      # colour_assessor(media_id) -> {"current", "suggestions"} or None
        self.notify = notify                        # notify(title, body, data) -> push to the owner's phone

    def _turn_config(self):
        """The business config plus the persona the dashboard has selected right now."""
        persona = persona_module.active(self.config, self.store)
        return {**self.config, "persona": persona} if persona else self.config

    def _owner(self, state):
        return (self.config.get("owner") or {}).get("name") or ("pasukan kami" if state.lang == "ms" else "our team")

    def _price(self, state, params=None):
        """The estimate from the chat's answers plus the owner's corrections (`params` overrides the saved ones)."""
        photo = from_dict(state.photo_assessment) if state.photo_assessment else None
        verified, overrides = views.engine_inputs(state, params)
        try:
            quote = compute_quotation(verified, self.config["pricing"], photo, overrides)
        except PricingError:
            return None                     # the team prices it by hand
        if state.estimated:
            quote.assumptions.append("customer estimated, not measured: " + ", ".join(state.estimated)
                                     + " (the larger figure of any range was used)")
        quote.assumptions.append("an estimate from the customer's own dimensions: the team confirms the "
                                 "real price after measuring on site")
        return quote

    def _reprice(self, state, params=None):
        quote = self._price(state, params)
        if quote is None:
            return None
        state.quote = quote.to_dict()
        state.quote_status = "needs_inspection" if quote.status == "needs_inspection" else "pending_approval"
        state.quote_stale = False
        return quote

    def _with_quote(self, state, reply):
        """When the job and contact details are complete, price once and keep the draft for the SME.
        The customer sees no number until the SME approves it. A size corrected afterwards re-prices the
        draft silently (until the SME has approved it)."""
        if "pricing" not in self.config or state.stage != "done":
            return reply
        uid = state.conversation_id
        if state.quote is not None:
            if state.quote_stale and state.quote_status in ("approved", "final"):
                was = state.quote.get("final_total") or state.quote.get("approved_total") or state.quote.get("total")
                quote = self._reprice(state)            # back to "waiting for approval" at the new price
                if quote is not None:
                    state.quote["previous_total"] = was
                    self.store.add_audit(uid, "customer", "state_change",
                                         f"The customer changed the job after the estimate was sent; re-priced at "
                                         f"{quote.currency} {quote.total:,.2f} (was {quote.currency} {was:,.2f})")
            elif state.quote_stale and state.quote_status in ("pending_approval", "needs_inspection"):
                quote = self._reprice(state)
                if quote is not None:
                    self.store.add_audit(uid, "system", "calculation", f"Draft recalculated after a corrected size: "
                                         f"{quote.currency} {quote.total:,.2f}")
            state.quote_stale = False
            return reply
        quote = self._price(state)
        if quote is None:
            return reply
        state.quote = quote.to_dict()
        fields = [{"field": k, "from": "", "to": str(v)} for k, v in state.verified.items()
                  if k not in ("customer_name", "phone")][:12]
        self.store.add_audit(uid, "ai", "ai_extraction", "The assistant collected the job details", fields)
        self.store.add_audit(uid, "system", "calculation", f"Draft estimate calculated: {quote.currency} {quote.total:,.2f}")
        if quote.status == "needs_inspection":
            state.quote_status, state.needs_human = "needs_inspection", True
            # replaces the closing line, which promised a quotation the customer will not get yet
            return t("inspection_wrap", state.lang, owner=self._owner(state), message=t("inspection_message", state.lang))
        state.quote_status = "pending_approval"
        return reply

    # --- the SME's side: quotes ------------------------------------------------------------------
    def quotes(self, status="pending_approval"):
        """Customers as the dashboard lists them, by the frontend's status (collecting, pending_approval,
        approved, needs_inspection, completed). Every price is an estimate until the site visit."""
        status = LEGACY_STATUS.get(status, status)
        booked = {b["user_id"] for b in self.store.bookings() if b["status"] == "confirmed"}
        return [views.quote_item(s, s.conversation_id in booked) for s in self.store.conversations()
                if views.front_status(s) == status]

    def pipeline(self):
        booked = {b["user_id"] for b in self.store.bookings() if b["status"] == "confirmed"}
        # every customer who has written, even one who has only said hello (no answers saved yet)
        return [views.quote_item(s, s.conversation_id in booked) for s in self.store.conversations()]

    def detail(self, user_id):
        """The review screen: job, quote, editable parameters, chat, photos, audit trail."""
        state = self.store.load(user_id)
        if not state.verified and not state.quote and not state.history:
            raise KeyError(user_id)
        booked = any(b["status"] == "confirmed" for b in self.store.bookings(user_id))
        return views.detail_view(state, self.store.messages(user_id), self.store.audit(user_id, 200), booked)

    def recalculate(self, user_id, params):
        """The engine's answer for the form's values, without saving them."""
        state = self.store.load(user_id)
        quote = self._price(state, params)
        if quote is None:
            raise ValueError("this job cannot be priced yet")
        data = quote.to_dict()
        return {"quote": views.quote_view(data), "duration_hours": (data.get("schedule") or {}).get("hours_on_site")}

    def save_params(self, user_id, params):
        """The owner's corrections: kept apart from what the assistant read, logged, and the draft re-priced."""
        with self.store.lock(user_id):
            state = self.store.load(user_id)
            if state.quote_status in ("approved", "final"):
                raise ValueError("this estimate was already sent; its values are locked")
            before = {**views.ai_values(state), **state.overrides}
            state.overrides = views.changed_params(state, params)
            after = {**views.ai_values(state), **state.overrides}
            changes = [{"field": k, "from": str(before.get(k)), "to": str(v)} for k, v in after.items()
                       if before.get(k) != v]
            quote = self._reprice(state)
            if changes:
                self.store.add_audit(user_id, "owner", "override", "The owner changed the job values", changes)
                if quote is not None:
                    self.store.add_audit(user_id, "system", "calculation",
                                         f"Recalculated: {quote.currency} {quote.total:,.2f}")
            self.store.save(state)
            return views.detail_view(state, self.store.messages(user_id), self.store.audit(user_id, 200), False)

    def send_owner_message(self, user_id, text, send):
        """The owner writes to the customer in the assistant's place (for example when it asked for a human).
        The assistant then stays quiet for a while so the two do not talk over each other. False if the send failed."""
        text = (text or "").strip()
        if not text or len(text) > 1000:
            raise ValueError("write a message of 1 to 1000 characters")
        with self.store.lock(user_id):
            state = self.store.load(user_id)
            if not (state.history or state.verified):
                raise KeyError(user_id)
            if not send(text):
                return False
            self.store.log_message(user_id, "owner", text)
            state.human_until, state.attention, state.needs_human = time.time() + TAKEOVER_SECONDS, False, False
            self.store.save(state)
            self.store.add_audit(user_id, "owner", "send", "The owner replied to the customer: " + text[:120])
            return True

    def resume_assistant(self, user_id):
        with self.store.lock(user_id):
            state = self.store.load(user_id)
            state.human_until = 0.0
            self.store.save(state)

    def audit_feed(self, limit=20):
        names = {s.conversation_id: views.customer_name(s) for s in self.store.conversations()}
        return [{**e, "customer": names.get(e["user_id"], e["user_id"]), "ts": views._iso(e["ts"])}
                for e in self.store.audit(None, limit)]

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

    def approve_quote(self, user_id, send, total=None, send_pdf=None, by=None):
        """SME approval. Sends the customer the estimate and how long the job takes (never the breakdown);
        the quote is marked approved only if the send worked. Raises ValueError when nothing is waiting."""
        with self.store.lock(user_id):
            state = self.store.load(user_id)
            # a job flagged for inspection can be approved too, once the owner has checked it (or decided it is fine)
            if state.quote_status not in ("pending_approval", "needs_inspection"):
                raise ValueError("no quote is waiting for approval")
            amount = state.quote["total"] if total is None else total
            message = approved_quote_message(amount, state.quote["currency"], self.config.get("business_name", "us"),
                                             state.lang, state.quote.get("schedule"), state.verified,
                                             pdf=send_pdf is not None)
            if state.quote.get("previous_total") is not None:
                message = f"{t('estimate_updated_intro', state.lang)}\n\n{message}"
            if not send(message):
                return False
            state.quote["approved_total"], state.quote_status = amount, "approved"
            state.waiting_count, state.attention, state.needs_human = 0, False, False
            self.store.save(state)
            self.store.log_message(user_id, "out", message)
            self.store.add_audit(user_id, "owner", "state_change",
                                 f"Estimate approved: {state.quote['currency']} {amount:,.2f}" + (f" by {by}" if by else ""))
            self.store.add_audit(user_id, "system", "send", "Estimate and duration sent to the customer on WhatsApp")
            if send_pdf is not None:
                from .pdf import estimate_pdf
                data = estimate_pdf(self.config.get("business_name", ""), views.customer_name(state),
                                    views.job_view(state), state.quote)
                if send_pdf(data, f"estimate-{self.config.get('business_name', 'painting').split()[0].lower()}.pdf"):
                    self.store.add_audit(user_id, "system", "send", "Estimate PDF sent to the customer on WhatsApp")
                else:
                    self.store.log_event("send_failed", f"{user_id}: the estimate PDF could not be sent")
            return True

    def reject_quote(self, user_id, reason, by=None):
        """The owner says no: nothing is sent to the customer and the job leaves the approval queue. Editing the
        job values re-prices it and puts it back in the queue. Raises ValueError when nothing is waiting."""
        reason = (reason or "").strip()
        if not reason:
            raise ValueError("a reason is required to reject an estimate")
        with self.store.lock(user_id):
            state = self.store.load(user_id)
            if state.quote_status not in ("pending_approval", "needs_inspection"):
                raise ValueError("no quote is waiting for approval")
            state.quote["rejected"] = {"reason": reason[:200], "by": by, "at": time.time()}
            state.quote_status, state.attention = "rejected", False
            self.store.save(state)
            self.store.add_audit(user_id, "owner", "state_change",
                                 f"Estimate rejected: {reason[:150]}" + (f" (by {by})" if by else ""))
            return True

    def confirm_final(self, user_id, send, total):
        """After the team has measured on site: send the final price. Raises ValueError unless the
        estimate was approved first."""
        with self.store.lock(user_id):
            state = self.store.load(user_id)
            if state.quote_status != "approved":
                raise ValueError("the estimate must be approved before a final price is confirmed")
            message = final_quote_message(total, state.quote["currency"], self.config.get("business_name", "us"),
                                          state.lang, state.verified)
            if not send(message):
                return False
            state.quote["final_total"], state.quote_status = total, "final"
            self.store.save(state)
            self.store.log_message(user_id, "out", message)
            self.store.add_audit(user_id, "owner", "state_change", f"Final price confirmed: {total:,.2f}")
            return True

    # --- the calendar: slots, bookings and the customer's yes or no ---------------------------------
    def _job_hours(self, state, fallback=4.0):
        return ((state.quote or {}).get("schedule") or {}).get("hours_on_site") or fallback

    def slots(self, user_id, busy=()):
        """Suggested start times for this customer's job, best first. A slot next to a job in the same area
        scores higher, so the crew's day stays compact. `busy` are events the dashboard already knows about."""
        state = self.store.load(user_id)
        anchor = datetime.fromtimestamp(state.created_at, scheduling.TZ) if state.created_at else None
        preference = scheduling.parse_preference(state.verified.get("preferred_datetime"), anchor,
                                                  today=datetime.now(scheduling.TZ).date())
        return scheduling.suggest_slots(self.store.bookings(), self._job_hours(state), state.verified.get("address", ""),
                                        extra_busy=[(b["start"], b["end"]) for b in busy], preference=preference,
                                        location=state.verified.get("location"))

    def booking_list(self, start=None, end=None):
        """Bookings overlapping [start, end] as the dashboard's Booking objects."""
        low = scheduling.parse_time(start) if start else None
        high = scheduling.parse_time(end) if end else None
        out = []
        for booking in self.store.bookings():
            if (low and scheduling.parse_time(booking["end"]) < low) or (high and scheduling.parse_time(booking["start"]) > high):
                continue
            for piece in views.booking_days_view(booking, self.store.load(booking["user_id"])):
                if (low and scheduling.parse_time(piece["end"]) < low) or (high and scheduling.parse_time(piece["start"]) > high):
                    continue
                out.append(piece)
        return out

    # --- demo data for filming: fake customers with quotes and a busy calendar ------------------------
    def seed_demo(self, now=None):
        """Replace any earlier demo data with a believable fortnight: customers in Klang Valley areas, their chats,
        priced estimates and bookings (one of them over three days). Every id starts with "demo-"."""
        from . import demo
        self.clear_demo()
        return demo.seed(self, now)

    def clear_demo(self):
        removed = 0
        for state in self.store.conversations():
            if state.conversation_id.startswith("demo-"):
                self.store.delete_conversation(state.conversation_id)
                removed += 1
        return removed

    def create_booking(self, user_id, start, end, send):
        """Offer a slot to the customer: stored as tentative, asked on WhatsApp, confirmed on their yes.
        Returns (booking view, whether the customer was messaged). Raises ValueError on a clash."""
        with self.store.lock(user_id):
            state = self.store.load(user_id)
            hours = self._job_hours(state, fallback=max(
                (scheduling.parse_time(end) - scheduling.parse_time(start)).total_seconds() / 3600, 1.0))
            address = state.verified.get("address", "")
            location = state.verified.get("location")
            if scheduling.conflicts(self.store.bookings(), start, hours, address, location=location):
                raise ValueError("that time overlaps another job")
            booking = scheduling.new_booking(user_id, views.customer_name(state), views.job_view(state)["phone"], address,
                                             start, hours, "tentative", location=location)
            self.store.save_booking(booking)
            when = scheduling.describe_when(booking["start"], state.lang)
            work = duration_text((state.quote or {}).get("schedule"), state.lang) or (
                f"{hours:g} jam kerja" if state.lang == "ms" else f"about {hours:g} hours of work")
            plan = scheduling.describe_days(booking, state.lang)
            message = t("booking_ask", state.lang, owner=self._owner(state), when=when,
                        text=work + (f" ({plan})" if plan else ""))
            notified = bool(send(message))
            if notified:
                self.store.log_message(user_id, "out", message)
                state.pending_booking = {"id": booking["id"], "reminded": False}
            self.store.save(state)
            self.store.add_audit(user_id, "owner", "schedule", f"Slot offered: {when}" + ("" if notified else
                                 " (customer could not be messaged)"))
            return views.booking_view(booking, state), notified

    def update_booking(self, booking_id, patch, send):
        """Move, confirm or cancel a booking. The customer is told about a move or a cancellation."""
        booking = self.store.get_booking(booking_id)
        if booking is None:
            raise KeyError(booking_id)
        user_id = booking["user_id"]
        with self.store.lock(user_id):
            state = self.store.load(user_id)
            booking = self.store.get_booking(booking_id)
            message = None
            if patch.get("start") and scheduling.parse_time(patch["start"]) != scheduling.parse_time(booking["start"]):
                if scheduling.conflicts(self.store.bookings(), patch["start"], booking["hours"], booking["address"],
                                        ignore_id=booking_id):
                    raise ValueError("that time overlaps another job")
                moved = scheduling.new_booking(user_id, booking["customer"], booking["phone"], booking["address"],
                                               patch["start"], booking["hours"], booking["status"])
                booking.update(start=moved["start"], end=moved["end"])
                if booking["status"] == "confirmed":
                    message = t("booking_moved", state.lang, when=scheduling.describe_when(booking["start"], state.lang))
            status = patch.get("status")
            if status in ("confirmed", "tentative", "cancelled") and status != booking["status"]:
                if status == "confirmed":
                    message = t("booking_ok", state.lang, when=scheduling.describe_when(booking["start"], state.lang),
                                owner=self._owner(state))
                elif status == "cancelled":
                    message = t("booking_cancelled", state.lang, owner=self._owner(state))
                booking["status"] = status
                if state.pending_booking and state.pending_booking.get("id") == booking_id:
                    state.pending_booking = None
            self.store.save_booking(booking)
            self.store.save(state)
            if message and send(message):
                self.store.log_message(user_id, "out", message)
            self.store.add_audit(user_id, "owner", "schedule", f"Booking {booking['status']}: "
                                 f"{scheduling.describe_when(booking['start'], 'en')}")
            return views.booking_view(booking, state)

    def delete_booking(self, booking_id, send):
        booking = self.update_booking(booking_id, {"status": "cancelled"}, send)
        self.store.delete_booking(booking_id)
        return booking

    def _booking_reply(self, state, text):
        """The customer's answer to an offered slot: a yes books it, a no (or another day) hands it back to the
        owner. None when the message is about something else."""
        pending = state.pending_booking
        booking = self.store.get_booking(pending["id"]) if pending else None
        if not booking or booking["status"] != "tentative":
            state.pending_booking = None
            return None
        uid, lang, owner = state.conversation_id, state.lang, self._owner(state)
        when = scheduling.describe_when(booking["start"], lang)
        if flow.is_yes(text):
            booking["status"], state.pending_booking = "confirmed", None
            self.store.save_booking(booking)
            self.store.add_audit(uid, "customer", "schedule", f"Customer accepted {when}")
            return t("booking_ok", lang, when=when, owner=owner)
        words = set(contact._words(text))
        if words & (contact.NEGATIVE | {"not"}) or flow._DATE_WORDS.search(text):
            booking["status"], state.pending_booking, state.attention = "cancelled", None, True
            if flow._DATE_WORDS.search(text):
                state.verified["preferred_datetime"] = " ".join(text.split())[:120]
            self.store.save_booking(booking)
            self.store.add_audit(uid, "customer", "schedule", f"Customer declined {when}: {text[:120]}")
            return t("booking_no", lang, owner=owner)
        if not pending.get("reminded"):
            pending["reminded"] = True
            return t("booking_remind", lang, when=when)
        return None

    # --- the customer's side -------------------------------------------------------------------
    def _answer(self, state, text):
        """The reply to one customer message, with the offered slot and the draft quote taken care of.
        While the owner is replying by hand the assistant only answers a slot offer and otherwise stays quiet."""
        if state.human_until > time.time():
            if state.pending_booking and state.stage == "done":
                reply = self._booking_reply(state, text)
                if reply is not None:
                    return reply
            state.attention = True
            return ""
        if state.pending_booking and state.stage == "done":
            reply = self._booking_reply(state, text)
            if reply is not None:
                return reply
        if self.colour_assessor and state.stage == "job" and state.awaiting_colour_photo and not state.last_photo_id \
                and _PHOTO_SENT.search(text):
            reply = t("colour_not_yet", state.lang)         # "I already sent it": it has not arrived yet
            state.add_turn(text, reply)
            return reply
        if self.colour_assessor and state.stage == "job" and flow.wants_colour_suggestion(text):
            return self._colour_reply(state, text)
        return self._with_quote(state, self.handler(state, text, self._turn_config(), self.client).reply)

    def _colour_options(self, state, result):
        names = [COLOUR_MS.get(c, c) if state.lang == "ms" else c for c in result["suggestions"]]
        options = ", ".join(names[:-1]) + (" atau " if state.lang == "ms" else " or ") + names[-1] if len(names) > 1 else names[0]
        current = result.get("current")
        if current:
            return t("colour_suggest", state.lang, options=options,
                     current=COLOUR_MS.get(current, current) if state.lang == "ms" else current)
        return t("colour_suggest_plain", state.lang, options=options)

    def _colour_reply(self, state, text):
        """Suggest colours from the customer's photo, or ask for the photo and remember why."""
        if not state.last_photo_id:
            state.awaiting_colour_photo = True
            reply = t("colour_need_photo", state.lang)
        else:
            reply = self._colour_from_photo(state)
        state.add_turn(text, reply)
        return reply

    def _colour_from_photo(self, state):
        state.awaiting_colour_photo = False
        try:
            result = self.colour_assessor(state.last_photo_id)
        except Exception:
            log.exception("colour suggestion failed for media %s", state.last_photo_id)
            result = None
        return self._colour_options(state, result) if result else t("colour_failed", state.lang)

    def _photo_reply(self, state, media_id):
        if media_id:
            state.last_photo_id = media_id
        assessment = None
        if self.photo_assessor and media_id:
            try:
                assessment = self.photo_assessor(media_id)
            except Exception:
                log.exception("photo assessment failed for media %s", media_id)
        if assessment is not None and not assessment.surface:
            self.store.log_event("photo_not_a_surface", f"{state.conversation_id}: {assessment.subject or 'unknown'}")
            return t("photo_not_surface", state.lang)               # a face or a t-shirt is not a wall
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
        started = time.time()
        try:
            result = self.transcriber(event.media_id)
        except Exception as err:
            log.exception("voice note transcription failed for media %s", event.media_id)
            self.store.log_event("voice_failed", f"{event.user_id}: {type(err).__name__}: {err}")
            return None, "failed"
        text = (result[0] if result else "").strip()
        language = result[1] if result and len(result) > 1 else ""
        self.store.log_event("voice_ok" if text else "voice_empty",
                             f"{event.user_id}: {len(text)} chars, language {language or '?'}, "
                             f"{time.time() - started:.1f}s")
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

    def _alert(self, state, before, event):
        """Push the owner when something now needs them: an estimate to approve, a customer asking for a person or
        changing the job, a booking answered. Only on the change, not on every later message."""
        if not self.notify:
            return
        human, attention, status, booking_id = before
        name = views.customer_name(state)
        data = {"user_id": state.conversation_id, "name": name}
        quote = state.quote or {}
        if state.quote_status != status and state.quote_status in ("pending_approval", "needs_inspection"):
            if state.quote_status == "needs_inspection":
                title, body = "Inspection needed", f"{name} needs a site inspection before a price"
            elif quote.get("previous_total") is not None and status in ("approved", "final"):
                title = "Changed job: approve the new price"
                body = (f"{name}: {quote.get('currency', '')} {quote.get('total', 0):,.2f} "
                        f"(was {quote.get('previous_total'):,.2f})")
            else:
                title, body = "Estimate to approve", f"{name}: {quote.get('currency', '')} {quote.get('total', 0):,.2f}"
        elif booking_id and not state.pending_booking:
            booking = self.store.get_booking(booking_id) or {}
            answer = "accepted" if booking.get("status") == "confirmed" else "declined"
            title, body = f"Booking {answer}", f"{name} {answer} the time you offered"
        elif (state.needs_human and not human) or (state.attention and not attention):
            said = (event.text or "").strip() or f"[{event.type}]"
            title, body = "A customer needs you", f"{name}: {said[:150]}"
        else:
            return
        try:
            self.notify(title, body, data)
        except Exception:
            log.exception("could not notify the owner")

    def erase_customer(self, user_id, by="the customer"):
        """PDPA: remove everything held about one customer (chat, photos, bookings, log). Returns False if unknown."""
        with self.store.lock(user_id):
            state = self.store.load(user_id)
            if not (self.store.messages(user_id) or state.history or state.consent or state.pending_first or state.verified):
                return False                                      # nothing is held about this customer
            self.store.delete_conversation(user_id)
            self.store.log_event("data_erased", f"{user_id} erased by {by}")
            return True

    def _consent_gate(self, state, event):
        """Returns (replies, erased) when the PDPA notice decides this message, else None. Nothing a customer sends is
        read, saved or sent to a model until they answer the notice with 1; STOP erases everything."""
        if not consent.required(self.config) or event.channel == "voice":
            return None
        text = event.text if event.type == "text" else ""
        owner = self._owner(state)
        if consent.withdraws(text) and state.consent in ("granted", "pending", "declined"):
            lang = state.lang
            self.store.delete_conversation(event.user_id)
            self.store.log_event("data_erased", f"{event.user_id} withdrew consent")
            return [t("consent_withdrawn", lang)], True
        if state.consent == "granted":
            return None
        if state.consent == "" and not state.history and not state.verified:
            if event.type == "text" and text.strip():
                state.pending_first = text.strip()[:1000]       # held unread, replayed once they agree
            state.lang = detect(text, state.lang) if text else state.lang
            state.consent, state.consent_asks = "pending", 1
            state.greeted = False
            return [t("consent_notice", state.lang, business=self.config.get("business_name", "Gesir.AI"), owner=owner)], False
        if state.consent == "":                                  # a chat that began before consent was required
            state.consent = "pending"
        if consent.agrees(text):
            state.consent, state.consent_at = "granted", time.time()
            self.store.add_audit(event.user_id, "customer", "consent",
                                 f"Agreed to the PDPA notice ({(self.config.get('privacy') or {}).get('notice_version', '')})")
            first, state.pending_first = state.pending_first, ""
            if first:
                self.store.log_message(event.user_id, "in", first)
                return [self._answer(state, first)], False
            return [f"{t('consent_thanks', state.lang)} {self._answer(state, 'hi')}".strip()], False
        if consent.declines(text):
            state.consent, state.pending_first = "declined", ""
            self.store.add_audit(event.user_id, "customer", "consent", "Declined the PDPA notice")
            return [t("consent_declined", state.lang, owner=owner)], False
        state.consent_asks += 1                                 # anything else: ask again, a few times, then stay quiet
        if state.consent_asks > consent.MAX_ASKS:
            return [], False
        return [t("consent_again", state.lang)], False

    def _handle_locked(self, event):
        state = self.store.load(event.user_id)
        gated = self._consent_gate(state, event)
        if gated is not None:
            replies, erased = gated
            if not erased:
                self.store.save(state)
            return replies
        before = (state.needs_human, state.attention, state.quote_status, (state.pending_booking or {}).get("id"))
        if not state.history and not state.channel:
            channel = {"name": clean_profile_name(event.profile_name),
                       "phone": clean_profile_phone(event.phone or "+" + event.user_id)}
            state.channel = {k: v for k, v in channel.items() if v}
        if not state.created_at:
            state.created_at = time.time()
        if event.channel == "voice":
            state.greeted = True        # the call greets the caller itself

        if event.type == "text" and event.text.strip():
            self.store.log_message(event.user_id, "in", event.text)
            reply = self._answer(state, event.text)
        elif event.type == "audio":
            self.store.log_message(event.user_id, "in", "[voice note]", event.media_id)
            text, problem = self._voice_text(event)
            if text is None:
                reply = t("voice_off" if problem == "off" else "voice_fail", state.lang)
            else:
                self.store.log_message(event.user_id, "in", text)
                answer = self._answer(state, text)
                heard = t("heard", state.lang, text=text[:200])
                reply = f"{heard} {answer}".strip() if answer else ""
        elif event.type == "image":
            self.store.log_message(event.user_id, "in", event.text, event.media_id)
            reply = self._photo_reply(state, event.media_id)
            caption = event.text.strip()
            suggested = False
            if self.colour_assessor and (state.awaiting_colour_photo or flow.wants_colour_suggestion(caption)):
                reply = f"{reply} {self._colour_from_photo(state)}".strip()     # the photo is what they were asked for
                suggested = True
                if flow.wants_colour_suggestion(caption):
                    caption = ""
            nxt = state.next_missing(self.config) if state.stage == "job" else None
            if suggested and not caption:
                pass                                        # the colour question is already asked
            elif caption and state.stage != "done":
                # "<photo> 5 here is an image for it too": the words with the photo are a message as well
                self.store.log_message(event.user_id, "in", caption)
                answer = self._answer(state, caption)
                reply = f"{reply} {answer}".strip()
            elif nxt:
                reply += " " + ask_for(nxt, state)
            elif state.stage == "job" and state.service_checked and self._turn_config().get("persona"):
                reply += " " + flow.contact_intro(state)      # the photo answered the last open question
        elif event.type == "location":
            place = event.location or {}
            lat, lon = place.get("lat"), place.get("lon")
            state.verified["location"] = {**place}
            self.store.log_message(event.user_id, "in", "[location] " + (event.text or f"{lat:.5f}, {lon:.5f}"))
            if state.stage == "job" and state.next_missing(self.config) == "address":
                label = event.text or t("pinned", state.lang, lat=lat, lon=lon)
                state.verified["address"] = label                               # the shared location is the address
                reply = advance(state, self._turn_config(), label, t("location_saved", state.lang))
            else:
                reply = t("location_saved", state.lang)
        elif event.type == "unsupported":
            self.store.log_message(event.user_id, "in", "[unsupported message type]")
            reply = t("unsupported", state.lang)
        else:
            return []

        self.store.save(state)
        if reply:
            self.store.log_message(event.user_id, "out", reply)
        self._alert(state, before, event)
        return [reply] if reply else []
