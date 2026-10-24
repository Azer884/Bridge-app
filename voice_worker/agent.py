"""LiveKit voice agent that answers WhatsApp calls for the painting assistant.

It runs as its own process (not inside the Replit web app). LiveKit's WhatsApp connector puts the caller in a room and
dispatches this agent by name; the agent listens (speech to text), asks the assistant what to say (backend.py), and speaks
the answer (text to speech). Interruptions are handled by LiveKit: when the caller talks over the agent, it stops.

Run (after `pip install -r voice_worker/requirements.txt` and setting the variables in voice_worker/README.md):
    python -m voice_worker.agent dev        # while testing
    python -m voice_worker.agent start      # for real use
This file has not been run against LiveKit Cloud yet: see voice_worker/README.md for the first-call checklist.
"""
import asyncio
import json
import logging
import os
import random
import time
from collections.abc import AsyncIterable

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession, FunctionTool, ModelSettings, inference, llm

from .backend import Backend, keyterms

load_dotenv(".env.local")
load_dotenv()
log = logging.getLogger("voice-agent")

AGENT_NAME = os.environ.get("WHATSAPP_LIVEKIT_AGENT_NAME", "orbyte-whatsapp")
RECORDING_NOTICE = os.environ.get("VOICE_RECORDING_NOTICE", "This call will be recorded and transcribed.")
GREETING = os.environ.get("VOICE_GREETING", f"Hello, thanks for calling. {RECORDING_NOTICE} How can I help you today?")
# Said while the assistant works, picked at random so the caller does not hear the same words every time. No full
# stops: a full stop at the end of a short line can be read aloud as "dot". VOICE_FILLERS replaces the English list
# ("|" between lines).
FILLERS = {
    "en": [s.strip() for s in os.environ.get("VOICE_FILLERS", "One moment please|Just a moment|Give me a second|"
                                             "Let me check that for you|Bear with me a moment").split("|") if s.strip()],
    "ms": ["Sekejap ya", "Tunggu sebentar", "Biar saya semak dulu", "Sebentar ya"],
}
FILLERS_AGAIN = {
    "en": ["Still working on it, thank you for waiting", "Almost there, thanks for your patience",
           "Thanks for holding, I'm nearly done"],
    "ms": ["Masih menyemak, terima kasih kerana menunggu", "Hampir siap, terima kasih kerana bersabar"],
}
GOODBYE = {
    "en": os.environ.get("VOICE_GOODBYE", "Thank you for calling, have a great day. Goodbye"),
    "ms": "Terima kasih kerana menelefon. Selamat tinggal",
}
FILLER_AFTER = float(os.environ.get("VOICE_FILLER_AFTER_SECONDS", "4"))      # a slow answer gets a short "one moment"
FILLER_EVERY = float(os.environ.get("VOICE_FILLER_EVERY_SECONDS", "20"))     # and a reminder now and then
CHAT_POLL = float(os.environ.get("VOICE_CHAT_POLL_SECONDS", "2"))            # how often to look for chat messages/photos
GIVE_UP_AFTER = float(os.environ.get("VOICE_GIVE_UP_AFTER_SECONDS", "240"))     # a cold photo model can take minutes
SORRY = os.environ.get("VOICE_SORRY", "Sorry, I am having trouble right now. A team member will get back to you.")


class PaintingAssistant(Agent):
    """The words come from the painting assistant's own backend, not from a language model chosen here."""

    def __init__(self, backend):
        super().__init__(instructions="Relay the business's assistant. Its replies come from the backend.")
        self.backend = backend
        self._heard, self._task = "", None
        self.end_call, self._last_filler = False, ""

    def _filler(self, again=False):
        """A "one moment" line in the caller's language, never the same one twice in a row."""
        options = (FILLERS_AGAIN if again else FILLERS).get(self.backend.lang) or (FILLERS_AGAIN if again else FILLERS)["en"]
        choices = [o for o in options if o != self._last_filler] or options
        self._last_filler = random.choice(choices)
        return self._last_filler

    async def on_user_turn_completed(self, turn_ctx: llm.ChatContext, new_message: llm.ChatMessage) -> None:
        """The caller finished a sentence: ask the assistant now, and if it is slow say "one moment" out loud while
        it works. This is a speech of its own. Text yielded from llm_node would wait inside LiveKit's sentence
        splitter (it holds back sentences under 20 characters) and only be heard together with the answer."""
        heard = (new_message.text_content or "").strip()
        if not heard:
            return
        started = time.monotonic()
        log.info("caller said: %r", heard[:120])
        self._heard, self._task = heard, asyncio.create_task(self.backend.ask(heard))
        done, _ = await asyncio.wait({self._task}, timeout=FILLER_AFTER)
        spoke = 0
        while not done and time.monotonic() - started < GIVE_UP_AFTER:
            log.info("the assistant is slow (%.1fs): saying a filler", time.monotonic() - started)
            await self.session.say(self._filler(again=bool(spoke)), add_to_chat_ctx=False)
            spoke += 1
            done, _ = await asyncio.wait({self._task}, timeout=FILLER_EVERY if spoke else FILLER_AFTER)

    async def llm_node(self, chat_ctx: llm.ChatContext, tools: list[FunctionTool],
                       model_settings: ModelSettings) -> AsyncIterable[str]:
        heard = ""
        for item in reversed(chat_ctx.items):
            if getattr(item, "role", None) == "user":
                heard = (item.text_content or "").strip()
                break
        if not heard:
            return
        task = self._task if self._task is not None and self._heard == heard else asyncio.create_task(
            self.backend.ask(heard))
        self._heard, self._task = "", None
        started = time.monotonic()
        try:
            reply = await asyncio.wait_for(task, timeout=GIVE_UP_AFTER)
        except Exception:
            log.exception("the assistant did not answer in time")
            reply = SORRY
        log.info("assistant answered after %.1fs: %r", time.monotonic() - started, reply[:120])
        if reply:
            yield reply
        if self.backend.end_call:
            self.end_call = True                # the job is complete or the caller said goodbye: hang up after this
        language = self.backend.lang
        tts = getattr(self.session, "tts", None)
        if language and hasattr(tts, "update_options"):
            try:
                tts.update_options(language=language)               # follow the customer's language
            except Exception:
                log.warning("could not switch the voice language to %s", language)


server = AgentServer()


@server.rtc_session(agent_name=AGENT_NAME)
async def entrypoint(ctx: agents.JobContext):
    meta = json.loads(ctx.job.metadata or "{}")
    call_id = meta.get("call_id") or ctx.room.name
    backend = Backend(os.environ["VOICE_BACKEND_URL"], os.environ["INCOMING_API_KEY"],
                      meta.get("user_id") or f"call-{call_id}", call_id)
    persona = await backend.persona()                      # each character has its own voice and name
    voice = persona.get("voice") or os.environ["VOICE_TTS_VOICE"]
    greeting = (f"Hello, this is {persona['name']}. {RECORDING_NOTICE} How can I help you today?"
                if persona.get("name") else GREETING)
    log.info("call from %s, character %s", backend.user_id, persona.get("name") or "(default)")
    session = AgentSession(
        # One backend call per finished turn. Preemptive generation would send a message to the assistant for every
        # partial transcript ("Hello?", "Hello? I want to paint...") and each one is stored as a customer message.
        preemptive_generation=False,
        min_endpointing_delay=float(os.environ.get("VOICE_MIN_ENDPOINTING_DELAY", "0.7")),
        max_endpointing_delay=float(os.environ.get("VOICE_MAX_ENDPOINTING_DELAY", "3.0")),
        min_interruption_words=2,                  # one stray word or an echo of the agent does not cut it off
        stt=inference.STT(model=os.environ.get("VOICE_STT_MODEL", "deepgram/nova-3"),
                          language=os.environ.get("VOICE_STT_LANGUAGE", "multi"),     # English and Malay together
                          extra_kwargs={"keyterm": keyterms()}),
        llm=inference.LLM(model=os.environ.get("VOICE_UNUSED_LLM", "openai/gpt-4.1-mini")),   # llm_node replaces it
        tts=inference.TTS(model=os.environ.get("VOICE_TTS_MODEL", "cartesia/sonic-3.5"),
                          voice=voice, language="en",
                          extra_kwargs={"speed": float(os.environ.get("VOICE_TTS_SPEED", "0.95"))}),    # calm, not rushed
    )
    assistant = PaintingAssistant(backend)
    ending = {"started": False}

    async def say_goodbye_and_hang_up():
        """The conversation is over: say goodbye, let it finish playing, then end the call for the caller too."""
        try:
            handle = session.say(GOODBYE.get(backend.lang) or GOODBYE["en"], allow_interruptions=False,
                                 add_to_chat_ctx=False)
            await handle
            await asyncio.sleep(1.0)
        finally:
            log.info("call finished: hanging up")
            try:
                await ctx.delete_room()
            except Exception:
                log.exception("could not end the call")
                ctx.shutdown("call finished")

    @session.on("agent_state_changed")
    def _agent_state(event):
        log.info("agent: %s -> %s", event.old_state, event.new_state)
        if event.new_state == "listening" and assistant.end_call and not ending["started"]:
            ending["started"] = True            # the last answer has been spoken
            asyncio.create_task(say_goodbye_and_hang_up())

    @session.on("user_state_changed")
    def _user_state(event):
        log.info("caller: %s -> %s", event.old_state, event.new_state)

    @session.on("error")
    def _session_error(event):
        log.error("session error: %s", getattr(event, "error", event))

    async def relay_chat():
        """Photos and messages the caller sends in the WhatsApp chat during the call are answered out loud."""
        while True:
            try:
                for text in await backend.pending():
                    log.info("telling the caller about their chat: %r", text[:100])
                    await session.say(text)
            except Exception:
                log.exception("could not relay a chat answer to the call")
            await asyncio.sleep(CHAT_POLL)

    async def call_over():
        relay.cancel()
        await backend.pending(end=True)            # answers to the chat go back to WhatsApp

    await session.start(room=ctx.room, agent=assistant)
    await backend.pending()                        # marks the call live: chat answers now come to the phone
    relay = asyncio.create_task(relay_chat())
    ctx.add_shutdown_callback(call_over)
    await asyncio.sleep(1.0)                       # let the caller's audio path settle before the greeting
    await session.say(greeting)


if __name__ == "__main__":
    agents.cli.run_app(server)
