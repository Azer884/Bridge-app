# Gesir.AI

> A WhatsApp AI assistant for service SMEs. It talks to customers on the owner's behalf, collects the job details, prepares a price estimate and a schedule, and asks the owner's permission before anything is sent.

The first version is built for Malaysian painting businesses.

---

## Team Information

| Field                  | Details                                     |
| ---------------------- | ------------------------------------------- |
| **Team Name**          |  HRISSA                                     |
| **Team Domain**        |  Domain 2                                   |
| **Main SDG**           |SDG 8 - Descent work and economic growth     |
|   **Sub SDG**          |SDG 8.1: Economic Growth, SDG8.2 Diversification and Innovation, SDG 8.3: Enterprise Support|
| **Team Leader**        | Azer Hamdaoui                               |
| **University**         |Xiamen University Malaysia                   |
| **Number of Members**  | 5                                           |

## Links

| Resource          | Link                                           |
| ----------------- | ---------------------------------------------- |
| GitHub Repository | https://github.com/Azer884/Bridge-app          |
| Replit Project    | https://replit.com/@AzerHamdaoui/Bridge-app    |
| Live Demo         | https://gesir-ai.replit.app (the dashboard is at `/app`; demo password: `TiJedWeldikYa5ra3fest3al5ra9omtnl9a5ryaBh8aElFarch`) |
| RunPod Endpoints  | text model `ose8agxpb9p1mr`, vision model `m3a8r7m8ebibba`, speech-to-text (Faster Whisper) `nvnrh39cdxgymr` (`https://api.runpod.ai/v2/<id>/runsync`) |
| Slide Deck        | https://canva.link/gesir-ai                    |
| Demo Video        | https://youtu.be/tXOuRwmwh6g              |

---

## Overview

### Problem
Many SMEs lose valuable time to constant back-and-forth with customers: clarifying what the job is, answering the same questions, negotiating a price and agreeing a date. It increases the owner's workload, delays decisions and takes attention away from the work itself.

### Solution
Gesir.AI sits on the business's WhatsApp number. It chats with the customer in English or Bahasa Malaysia, understands text, photos and voice notes, and asks one question at a time until it has the job details. It never invents information, and it never decides prices or bookings itself: a deterministic rate engine prepares the estimate, and the owner reviews, edits and approves it in a dashboard. The customer then receives the estimate, a note that it is only an estimate, and how long the job will take. Jobs are scheduled so that customers in the same area are visited close together.

### Key Features
Status: working means it runs in the live demo and is covered by tests. Voice notes and calls are still being finished.

- **Customer conversation (working)** — natural replies with a chosen persona, one question at a time, corrections ("nvm its 4m"), several messages in a row read as one, "start over", shared locations, and English or Malay with automatic switching.
- **Photos (working)** — a vision model reads the surface condition from the customer's photo (cracks, damp, peeling) and flags jobs that need an inspection.
- **Estimate and final price (working)** — Malaysian rate card in MYR. The owner sees the full breakdown; the customer only sees the total, the estimated time and an "estimate only" note. After the site visit the owner sends the final price.
- **Owner dashboard (working)** — quotes, a review screen (edit the values the AI read, recalculate, PDF preview), pipeline, customers, calendar, personas, and writing to a customer in the assistant's place.
- **Smart scheduling (working)** — suggests start times that match what the customer asked for ("Monday evening"), keeps jobs in the same area close together, adds travel time, and never double books. The customer confirms the offered slot on WhatsApp.
- **Voice notes (fix being deployed)** — transcribed with Whisper (English, Malay and Manglish) and handled like typed messages.
- **WhatsApp calls (in development)** — calls are accepted through LiveKit and answered by a voice agent that uses the same assistant. Not yet tested end to end.

See [`docs/STATUS.md`](docs/STATUS.md) for what is built and what is still missing.

### Tech Stack

| Layer         | Technology                                              |
| ------------- | ------------------------------------------------------- |
| Frontend      | React, TypeScript and Vite (web), Expo React Native (mobile). Source in `frontend/` (`web/`, `mobile/`, `shared/`); the web build is served from `dashboard/` |
| Backend       | Python 3.12, FastAPI, uvicorn                           |
| Database      | PostgreSQL on Replit (SQLite for local runs)            |
| AI / Compute  | RunPod serverless GPU: Qwen2.5-7B-Instruct (chat), Qwen2.5-VL-7B-Instruct (photos). Whisper (`faster-whisper`) for voice notes |
| Channels      | WhatsApp Cloud API (messages, photos, voice notes, calls), LiveKit Cloud for calls |
| Hosting / Dev | Replit                                                  |

---

## Project Structure

```
.
├── config/
│   └── business_config.example.json   # business, personas, required fields, Malaysian rate card
├── dashboard/                         # built web dashboard served by the backend (from feature/frontend)
├── docs/
│   └── STATUS.md                      # what works, what is missing, how to link Google Calendar
├── prompts/
│   └── painting_assistant.txt         # the assistant's permanent rules
├── scripts/                           # chat.py, quote.py, build_dashboard.sh and other helpers
├── src/
│   ├── server.py                      # FastAPI app: WhatsApp webhook, dashboard API, login, static site
│   ├── service.py                     # one incoming message -> replies; quotes, bookings, takeover
│   ├── assistant.py, flow.py          # the conversation: prefill, corrections, steps around the model
│   ├── prompt.py, validation.py,      # prompt building, grounding and screening of model output
│   │   grounding.py, guard.py
│   ├── pricing.py                     # deterministic estimate and working-hours engine
│   ├── scheduling.py                  # slot suggestions, area clustering, bookings
│   ├── calendar_scheduler.py          # the team's calendar rules (working hours, Google Calendar)
│   ├── whatsapp.py, events.py         # WhatsApp sending, media download, webhook parsing
│   ├── whatsapp_calling.py            # call hand-off to LiveKit
│   ├── transcribe.py, vision.py       # voice notes (Whisper) and photo assessment
│   ├── i18n.py, persona.py            # English and Malay texts, personas
│   ├── store.py                       # SQLite and PostgreSQL storage
│   └── views.py, pdf.py, webauth.py   # dashboard shapes, estimate PDF, dashboard login
├── voice_worker/                      # LiveKit voice agent that answers WhatsApp calls (own process)
├── voice-agent/                       # earlier local voice experiments (Whisper + TTS)
├── tests/                             # unit tests (unittest)
├── submission/                        # required submission documents
├── pyproject.toml, uv.lock            # Python dependencies (uv)
└── README.md
```

### Architecture

```
Customer ──► WhatsApp Cloud API ──► /webhook (Replit, FastAPI)
                                          │
              ┌───────────────────────────┼─────────────────────────────┐
              ▼                           ▼                             ▼
     rules, prefill, validation     RunPod GPU models            PostgreSQL
     (conversation, pricing,        (chat + photo reading)       (customers, jobs,
      scheduling in Python)                                       bookings, audit)
              │
              ▼
   Owner dashboard (/app) ── approve estimate, book slot, reply by hand ──► WhatsApp

Calls: WhatsApp call ──► LiveKit Cloud ──► voice_worker (speech to text, text to speech) ──► /incoming
```

The model only writes the conversation. Everything that matters (what to ask next, what counts as a stored answer, prices, availability, who is allowed to see what) is decided by code, and every extracted value is checked against what the customer actually wrote.

---

## How to Run

### Configuration

Set these in Replit **Secrets**, or in a local `.env` (never commit it). `.env.example` lists them.

| Variable | Purpose |
| -------- | ------- |
| `RUNPOD_API_KEY`, `RUNPOD_ENDPOINT_ID` | chat model endpoint |
| `RUNPOD_VISION_API_KEY`, `RUNPOD_VISION_ENDPOINT_ID` | photo model endpoint |
| `STT_RUNPOD_ENDPOINT_ID`, `STT_RUNPOD_API_KEY` | voice-note transcription on RunPod's Faster Whisper endpoint; empty means the server transcribes on its own CPU |
| `INCOMING_API_KEY` | shared key for incoming messages, dashboard scripts, and voice worker |
| `VAPI_API_KEY` | separate Bearer key for the Vapi Custom LLM endpoint |
| `DASHBOARD_PASSWORD`, `SESSION_SECRET` | dashboard sign-in and its cookie signing |
| `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_APP_SECRET` | receiving WhatsApp webhooks |
| `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID` | sending messages, downloading photos and voice notes |
| `DATABASE_URL` | PostgreSQL (Replit sets it); without it a local SQLite file is used |
| `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `WHATSAPP_LIVEKIT_AGENT_NAME` | WhatsApp calls (see `voice_worker/README.md`) |
| `CORS_ORIGINS`, `STT_MODEL_SIZE`, `MESSAGE_WINDOW_SECONDS` | optional |

### Connect a Vapi phone assistant

Bridge exposes an OpenAI-compatible `POST /chat/completions` endpoint. It sends
each caller turn through the same painting assistant used by WhatsApp, including
screening, job-state updates, price rules, and response validation. When Vapi
provides the caller's phone number, Bridge reuses that customer's existing
conversation. Otherwise, Bridge keeps state under the Vapi call ID.

In Vapi, select **Custom LLM** and set the endpoint base URL to
`https://gesir-ai.replit.app`. Vapi appends `/chat/completions`. Create a Bearer
credential whose token matches Replit's `VAPI_API_KEY`, then attach it to the
assistant. Generate this as a separate secret; do not reuse `INCOMING_API_KEY`.
Keep call metadata enabled so Bridge can identify each call.
Vapi continues to provide telephony, transcription, and speech playback; Bridge
provides the assistant response. Use the separate LiveKit worker setup below
for calls made to the WhatsApp Business number.

### Option 1 — Run on Replit (recommended)

1. Open the [Replit Project](https://replit.com/@AzerHamdaoui/Bridge-app), or import this repository with **Create Repl → Import from GitHub**.
2. Add the secrets above. Add a PostgreSQL database in the Replit **Database** tool.
3. Dependencies come from `pyproject.toml` (Replit uses uv). Click **Run**, or publish with Replit **Deployments** (Reserved VM).
4. In the Meta developer dashboard, set the WhatsApp callback URL to `https://<your-app>.replit.app/webhook` with your verify token, and subscribe to `messages` (and `calls` for calls).
5. Open `https://<your-app>.replit.app/app`, sign in with `DASHBOARD_PASSWORD`.

### Option 2 — Run locally

```bash
git clone https://github.com/Azer884/Bridge-app.git
cd Bridge-app
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install fastapi uvicorn              # add faster-whisper "av<19" and "psycopg[binary,pool]" for voice notes and PostgreSQL
pip install httpx                        # only needed to run the tests
cp .env.example .env            # then fill in your values
uvicorn src.server:create_app --factory --port 8000
```

Without `DATABASE_URL` the app keeps its data in `data/bridge.db`. To rebuild the dashboard from the frontend branch, use `scripts/build_dashboard.sh`.

### Run Tests

```bash
python -m unittest discover tests
```

Tests use a fake model and need no network. The PostgreSQL tests run only when `TEST_DATABASE_URL` is set.

### Mobile App (Android)

The mobile app is an Expo React Native app in `frontend/mobile/`. It shares one typed API client with the web dashboard (`frontend/shared/`) and has the same screens: quote review, pipeline, calendar, customers, personas, WhatsApp link and status.

**Run in development**

```bash
cd frontend/mobile
npm install
cp .env.example .env     # set EXPO_PUBLIC_USE_MOCK=false, EXPO_PUBLIC_API_URL and EXPO_PUBLIC_API_KEY for the real backend
npx expo start           # scan the QR code with Expo Go, or press a for an Android emulator
```

With `EXPO_PUBLIC_USE_MOCK=true` (the default in `.env.example`) the app runs on sample data and needs no backend. On a phone, `EXPO_PUBLIC_API_URL` must be a reachable URL (the Replit URL or your PC's LAN IP), not `localhost`.

**Try the Android app**

Download the dashboard app for Android: [Gesir dashboard APK](https://expo.dev/artifacts/eas/6ZV8hhM0K5X0U1nYQwdo0DmjPcMcjK6iT5dhvIhgdio.apk). Open the link on an Android phone, install the downloaded file, and allow "install unknown apps" if Android asks. It connects to the live backend at `https://Gesir-AI.replit.app`.

**Build the APK** (cloud build with EAS, no Android SDK needed)

```bash
cd frontend/mobile
npm install -g eas-cli            # or prefix the commands below with npx
eas login
eas init                          # links the project to your Expo account (edits app.json)
eas env:create preview --name EXPO_PUBLIC_API_KEY --value <INCOMING_API_KEY> --visibility sensitive
eas build -p android --profile preview
```

`eas.json` defines the `preview` profile: it builds an `.apk`, turns sample data off, points at `https://Gesir-AI.replit.app` and enables live bookings. Change `EXPO_PUBLIC_API_URL` there if your backend is elsewhere. When the build finishes EAS prints a download link; open it on the phone and install the APK (allow "install unknown apps" if Android asks).

**Security:** `EXPO_PUBLIC_` values are bundled into the app, so the `INCOMING_API_KEY` is inside the APK and can be extracted. The download link above is public for the hackathon judging; rotate `INCOMING_API_KEY` (on Replit and in the EAS `preview` environment) and rebuild the app once judging is over, and add real per-user login before any production use.

---

## How We Use Replit *(Required)*

- **Development:** the backend and the dashboard are developed in the shared Repl and in GitHub; Replit's shell is used for dependency changes (`uv add`) and checks.
- **Hosting:** the FastAPI app (WhatsApp webhook, dashboard API and the built dashboard) is deployed with Replit Deployments at the Live Demo link above, on a Reserved VM.
- **Database:** conversations, jobs, bookings and the audit trail are stored in Replit's PostgreSQL, so data survives republishing.
- **Secrets:** every API key and token lives in Replit Secrets, never in the code.

📄 Proof of use: [`submission/REPLIT PROOF OF USE.pdf`](submission/REPLIT%20PROOF%20OF%20USE.pdf)

## How We Use RunPod *(Required)*

- **Workload:** both AI models run on RunPod serverless GPU endpoints that use the vLLM worker: `Qwen/Qwen2.5-7B-Instruct` writes the conversation and `Qwen/Qwen2.5-VL-7B-Instruct` reads photos of the walls. Voice notes are transcribed on RunPod's Faster Whisper endpoint (`nvnrh39cdxgymr`).
- **Integration:** `src/runpod_client.py` calls the endpoints with `RUNPOD_API_KEY` and the endpoint ids, and polls for the result when a worker is cold-starting (2 to 5 minutes). The dashboard's Status page shows each model's readiness.
- **Cost control:** the endpoints scale to zero when idle. For a live demo, set Min Workers to 1.

Example request:

```bash
curl -X POST https://api.runpod.ai/v2/$RUNPOD_ENDPOINT_ID/runsync \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input": {"messages": [{"role": "user", "content": "Hello"}], "sampling_params": {"max_tokens": 50}}}'
```

📄 Proof of use: [`submission/RUNPOD PROOF OF USE.pdf`](submission/RUNPOD%20PROOF%20OF%20USE.pdf)

---

## Challenges & Learnings

- **Trusting a small model.** A 7B model sometimes invented values, asked two questions, or wrote plain text instead of the required format. We moved every decision into code: the backend picks the next question, checks each extracted value against the customer's own words, reads simple answers itself, retries and then falls back to a safe template.
- **Real customers are messy.** Chats showed people changing their mind, sending several messages at once, guessing sizes, writing in Malay or Manglish and sending locations. Each case became a rule with a regression test.
- **Cold starts and hosting limits.** GPU workers take minutes to wake and Replit deployments lose local files on every republish. We added graceful waiting messages, a status view, and PostgreSQL.
- **Debugging without logs.** Production logs were not readable, so the app records its own event trail (`/api/events`), which found the expired WhatsApp token and a PyAV version clash that broke voice notes.
- **Prices must be explainable.** The estimate is deterministic, uses Malaysian market rates, is always labelled as an estimate (customers can give wrong sizes), and the owner can correct any value before it is sent.

## Future Improvements

- [ ] Confirm voice notes and WhatsApp calls end to end in the live demo
- [ ] Link Google Calendar on the server and exclude Malaysian public holidays
- [ ] WhatsApp message templates, so estimates and slot offers work after the 24-hour window
- [ ] Rate card and working-hours editor in the dashboard, with the SME's real prices
- [ ] Owner notifications (WhatsApp or push) for new quotes and messages that need a person
- [ ] Customer reschedule and cancel, and day-before reminders
- [ ] Per-user logins, privacy consent and data deletion

## Team

| Name              | Role                                       | GitHub                                   |
| -----------       | -------------------------------------------| ---------------------------------------- |
| Azer Hamdaoui     | Team Lead / Runpod/ AI Expert               | [@Azer884](https://github.com/Azer884) |
| Omar Bouhlel      | Frontend / AI-calendar Developer           | [@omarbouuhlel](https://github.com/omarbouuhlel) |
| Tarek ben slimen  | AI-whatsapp voice/call Messages Expert     | [@Trexgames4324](https://github.com/Trexgames4324) |
| Ilyess Hassine    | Whatsapp Linkage Analyzer                  | [@ilyesshassine](https://github.com/ilyesshassine) |
| Moetez Soltani    | Representater / Organizer                  |[@Moe-MY](https://github.com/Moe-MY)|

---

## Submission Checklist

- [ ] Team name, domain (Domain 1 / Domain 2) and SDG track filled in
- [ ] Slide deck link added
- [ ] Demo video link added
- [ ] Replit used, with proof of use in `submission/`
- [ ] RunPod used, with proof of use in `submission/`
- [ ] Submission template completed in `submission/`
- [ ] "How to Run" steps verified
- [ ] No API keys or secrets committed to the repository

## License

This project is licensed under the [Apache License 2.0](LICENSE).
