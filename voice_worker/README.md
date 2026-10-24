# Voice agent for WhatsApp calls

The web app (Replit) accepts the call and hands it to LiveKit Cloud; this worker is the voice that answers. It is a separate
process: run it on your own computer for the demo, or deploy it to LiveKit Cloud (`lk agent create`).

```
customer calls the WhatsApp number
  -> Meta `calls` webhook -> /webhook (Replit) -> LiveKit Cloud accepts the call into a room
  -> LiveKit dispatches the agent named WHATSAPP_LIVEKIT_AGENT_NAME to the room
  -> this worker: speech to text -> POST /incoming (the same assistant as the chat) -> text to speech
```
Because the agent is told the caller's WhatsApp number, the call continues that customer's chat: same job, same quote.

## Setup
1. LiveKit Cloud project (free to start). Note the URL, API key and API secret. WhatsApp calling only works on LiveKit Cloud.
2. Replit Secrets (the web app): `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `WHATSAPP_CALLING_ENABLED=true`
   (optional: `WHATSAPP_LIVEKIT_AGENT_NAME`, default `orbyte-whatsapp`; `WHATSAPP_CALL_GRAPH_API_VERSION`, default `26.0`).
   Add the package there once: `uv add "livekit-api>=1.2.2,<2"`.
3. Meta (WhatsApp, Configuration): subscribe the same webhook to the **calls** field, use API version 23.0 or newer on every
   field, and set the business's call hours. Calling must be enabled for the number in WhatsApp Manager (Meta limits who can use it).
4. This worker, on any machine with Python 3.10+:
   ```
   pip install -r voice_worker/requirements.txt
   ```
   `.env.local` next to where you run it:
   ```
   LIVEKIT_URL=...
   LIVEKIT_API_KEY=...
   LIVEKIT_API_SECRET=...
   VOICE_BACKEND_URL=https://gesir-ai.replit.app
   INCOMING_API_KEY=...            # same value as the Replit secret
   VOICE_TTS_VOICE=...             # a Cartesia voice id you picked in the Cartesia playground (English and Malay speakers)
   ```
   Then `python -m voice_worker.agent dev`.
   Speech models are LiveKit Inference strings, billed through LiveKit Cloud: `VOICE_STT_MODEL` (default `deepgram/nova-3`,
   language `multi` covers English and Malay), `VOICE_TTS_MODEL` (default `cartesia/sonic-3.5`).

## Run it on your own computer (Windows)
1. `python -m venv .venv-voice` then `.venv-voice\Scripts\python -m pip install -r voice_worker/requirements.txt` (once).
2. Fill the empty lines in `.env.local` (it is git-ignored): the LiveKit key and secret, `INCOMING_API_KEY`, `VOICE_TTS_VOICE`.
3. Double-click `voice_worker/run_local.cmd`, or run `.venv-voice\Scripts\python -m voice_worker.check` and then
   `.venv-voice\Scripts\python -m voice_worker.agent dev`. The check says what is missing, whether the assistant answers,
   whether `INCOMING_API_KEY` is accepted and whether LiveKit accepts the keys. Leave the window open: calls are only answered
   while the worker runs.

## First-call checklist (this has not been run end to end yet)
1. `GET /api/events` on the web app should show `webhook ... 1 call event(s)` then `call_handled connect ...` when someone calls.
   `call_error` has the reason (missing LiveKit secrets, no agent running, call outside the call hours).
2. If the caller hears nothing: the worker is not running or cannot reach `VOICE_BACKEND_URL`. With the default
   `WHATSAPP_CALL_WAIT_FOR_AGENT=true` an absent agent makes the call fail rather than sit silent.
3. A slow answer (the AI model waking up takes minutes) makes the agent say "One moment please"; after 90 seconds it apologises.
4. Check the voice language switch (`tts.update_options(language=...)`) with a Malay caller; if your LiveKit version does not
   support it the agent keeps speaking English and logs a warning.
