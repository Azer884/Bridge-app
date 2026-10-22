"""One incoming event -> the replies to send. Channel-neutral: no HTTP, no WhatsApp here."""
from .assistant import handle_message
from .guard import clean_profile_name, clean_profile_phone
from .schema import FIELDS

PHOTO_REPLY = "Thanks, I've passed your photo to our team to look at."
UNSUPPORTED_REPLY = "Sorry, I can only read text messages and photos at the moment."


class IncomingService:
    def __init__(self, store, config, client, handler=handle_message):
        self.store, self.config, self.client, self.handler = store, config, client, handler

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
            reply = self.handler(state, event.text, self.config, self.client).reply
        elif event.type == "image":
            self.store.log_message(event.user_id, "in", event.text, event.media_id)
            reply = PHOTO_REPLY
            nxt = state.next_missing(self.config) if state.stage == "job" else None
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
