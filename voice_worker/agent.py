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
import time
from collections.abc import AsyncIterable

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession, FunctionTool, ModelSettings, inference, llm

from .backend import Backend

load_dotenv(".env.local")
load_dotenv()
log = logging.getLogger("voice-agent")

AGENT_NAME = os.environ.get("WHATSAPP_LIVEKIT_AGENT_NAME", "orbyte-whatsapp")
GREETING = os.environ.get("VOICE_GREETING", "Hello, thanks for calling. How can I help you today?")
FILLER = os.environ.get("VOICE_FILLER", "One moment please.")
FILLER_AFTER = float(os.environ.get("VOICE_FILLER_AFTER_SECONDS", "4"))      # a slow answer gets a short "one moment"
GIVE_UP_AFTER = float(os.environ.get("VOICE_GIVE_UP_AFTER_SECONDS", "90"))
SORRY = os.environ.get("VOICE_SORRY", "Sorry, I am having trouble right now. A team member will get back to you.")


class PaintingAssistant(Agent):
    """The words come from the painting assistant's own backend, not from a language model chosen here."""

    def __init__(self, backend):
        super().__init__(instructions="Relay the business's assistant. Its replies come from the backend.")
        self.backend = backend

    async def llm_node(self, chat_ctx: llm.ChatContext, tools: list[FunctionTool],
                       model_settings: ModelSettings) -> AsyncIterable[str]:
        heard = ""
        for item in reversed(chat_ctx.items):
            if getattr(item, "role", None) == "user":
                heard = (item.text_content or "").strip()
                break
        if not heard:
            return
        started = time.monotonic()
        log.info("caller said: %r", heard[:120])
        task = asyncio.create_task(self.backend.ask(heard))
        done, _ = await asyncio.wait({task}, timeout=FILLER_AFTER)
        if not done:
            log.info("the assistant is slow (%.1fs): saying a filler", time.monotonic() - started)
            yield FILLER
        try:
            reply = await asyncio.wait_for(task, timeout=GIVE_UP_AFTER)
        except Exception:
            log.exception("the assistant did not answer in time")
            reply = SORRY
        log.info("assistant answered after %.1fs: %r", time.monotonic() - started, reply[:120])
        if reply:
            yield reply
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
    session = AgentSession(
        # One backend call per finished turn. Preemptive generation would send a message to the assistant for every
        # partial transcript ("Hello?", "Hello? I want to paint...") and each one is stored as a customer message.
        preemptive_generation=False,
        min_endpointing_delay=float(os.environ.get("VOICE_MIN_ENDPOINTING_DELAY", "0.7")),
        max_endpointing_delay=float(os.environ.get("VOICE_MAX_ENDPOINTING_DELAY", "3.0")),
        min_interruption_words=2,                  # one stray word or an echo of the agent does not cut it off
        stt=inference.STT(model=os.environ.get("VOICE_STT_MODEL", "deepgram/nova-3"),
                          language=os.environ.get("VOICE_STT_LANGUAGE", "multi")),     # English and Malay together
        llm=inference.LLM(model=os.environ.get("VOICE_UNUSED_LLM", "openai/gpt-4.1-mini")),   # llm_node replaces it
        tts=inference.TTS(model=os.environ.get("VOICE_TTS_MODEL", "cartesia/sonic-3.5"),
                          voice=os.environ["VOICE_TTS_VOICE"], language="en"),
    )
    @session.on("agent_state_changed")
    def _agent_state(event):
        log.info("agent: %s -> %s", event.old_state, event.new_state)

    @session.on("user_state_changed")
    def _user_state(event):
        log.info("caller: %s -> %s", event.old_state, event.new_state)

    @session.on("error")
    def _session_error(event):
        log.error("session error: %s", getattr(event, "error", event))

    await session.start(room=ctx.room, agent=PaintingAssistant(backend))
    await asyncio.sleep(1.0)                       # let the caller's audio path settle before the greeting
    await session.say(GREETING)


if __name__ == "__main__":
    agents.cli.run_app(server)
