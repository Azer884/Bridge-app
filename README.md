> [!IMPORTANT]
> **Submission documents** are in [`submission/`](submission/): the Final report, the Technical & Tools Declaration, the Preliminary proposal, and the Replit and RunPod proofs of use.

# Gesir.AI

> A WhatsApp AI assistant for service SMEs. It talks to customers on the owner's behalf, collects the job details, prepares a price estimate and a schedule, and asks the owner's permission before anything is sent.

The first version is built for Malaysian painting businesses.

---

## Team Information

| Field                  | Details                                     |
| ---------------------- | ------------------------------------------- |
| **Team Name**          |  HRISSA                                     |
| **Team Domain**        |  Domain 2                                   |
| **Main SDG**           |SDG 8 - Decent work and economic growth      |
|   **Sub SDG**          |SDG 8.1: Economic Growth, SDG8.2 Diversification and Innovation, SDG 8.3: Enterprise Support|
| **Team Leader**        | Azer Hamdaoui                               |
| **University**         |Xiamen University Malaysia                   |
| **Number of Members**  | 5                                           |

## Links

| Resource          | Link                                           |
| ----------------- | ---------------------------------------------- |
| GitHub Repository | https://github.com/Azer884/Bridge-app          |
| Replit Project    | https://replit.com/@AzerHamdaoui/Bridge-app    |
| Live Demo         | https://gesir-ai.replit.app (the dashboard is at `/app`; create an account at `/signup`, choosing painting or aircon; both trades work for every account) |
| RunPod Endpoints  | text model `ose8agxpb9p1mr`, vision model `m3a8r7m8ebibba`, speech-to-text (Faster Whisper) `nvnrh39cdxgymr` (`https://api.runpod.ai/v2/<id>/runsync`) |
| Slide Deck        | https://canva.link/gesir-ai                    |
| Demo Video        | https://youtu.be/tXOuRwmwh6g              |

---

## Overview

### Problem
Many SMEs lose valuable time to constant back-and-forth with customers: clarifying what the job is, answering the same questions, negotiating a price and agreeing a date. It increases the owner's workload, delays decisions and takes attention away from the work itself.

### Solution
Gesir.AI sits on the business's WhatsApp number. It chats with the customer in English or Bahasa Malaysia, understands text, photos and voice notes, and asks one question at a time until it has the job details. It never invents information, and it never decides prices or bookings itself: a deterministic rate engine prepares the estimate, and the owner reviews, edits and approves it in a dashboard. The customer then receives the estimate, a note that it is only an estimate, and how long the job will take. Jobs are scheduled so that customers in the same area are visited close together.

### Who it is for
The owner and the small team of a Malaysian painting contractor who take every enquiry on WhatsApp. The recurring chore Gesir removes is **turning a WhatsApp enquiry into an approved quotation and a booked visit**: asking for the sizes, the surfaces and the condition, working out a price, writing it up and agreeing a date.

### Key Features
Status: working means it runs in the live demo and is covered by tests. Voice notes and calls are still being finished.

- **Customer conversation (working)** — natural replies with a chosen persona, one question at a time, corrections ("nvm its 4m"), several messages in a row read as one, "start over", shared locations, and English or Malay with automatic switching. It refuses jobs outside Malaysia, weekends, public holidays and times outside working hours.
- **Photos (working)** — a vision model reads the surface condition from the customer's photo (cracks, damp, peeling) and flags jobs that need an inspection.
- **Estimate and final price (working)** — priced from real 2026 Klang Valley market rates in MYR (see [`docs/PRICING.md`](docs/PRICING.md)), with the typical market range shown to the owner. The owner sees the full breakdown; the customer only sees the total, the estimated time and an "estimate only" note. After the site visit the owner sends the final price.
- **Owner dashboard in the Orbyte layout (working)** — Dashboard with Pending Actions (Approve, Review), Clients, Projects (each project opens the quote: what the AI read, the price, approve or reject, the chat, the PDF, the activity log), Users with roles, Wallet, Organization settings (WhatsApp, personas, model status) and the Job Calendar.
- **Smart scheduling (working)** — suggests start times that match what the customer asked for ("Monday evening"), keeps jobs in the same area close together, adds travel time, and never double books. Bookings respect the working day (9 am to 6 pm, lunch 1 to 2 pm) and skip weekends and public holidays. The customer confirms the offered slot on WhatsApp.
- **Roles and approval (working)** — Company Admin and Approver may approve or reject; a Reviewer may only read. The server checks the role on every approve and reject.
- **Voice notes (fix being deployed)** — transcribed with Whisper (English, Malay and Manglish) and handled like typed messages.
- **WhatsApp calls (in development)** — calls are accepted through LiveKit and answered by a voice agent that uses the same assistant. Not yet tested end to end.

---

## The Final Demo Journey

One SME, one task, one run: a customer asks for a repaint on WhatsApp and ends with an approved estimate and a booked visit.

| Step | What happens | Where to see it |
| ---- | ------------ | --------------- |
| 1. Trigger | A customer messages the business's WhatsApp number. The message arrives automatically on a signed webhook; nobody has to open an app. | Customer's WhatsApp, then **Dashboard** |
| 2. Connected data | Gesir pulls together the chat, the photos, the shared location, the business's rate card, the crew's calendar and its working rules. | **Projects** ▸ open a project |
| 3. Decision logic | Code decides what to ask next and prices the job with a deterministic engine. AI is used only to read free text and photos. Missing details are asked again; anything unclear (an inspection case, a customer asking for a person) is handed to the owner with the reason. | Project page: "Check before sending" |
| 4. Human approval | A person with the Approver or Company Admin role approves or rejects. Nothing is sent before that. A rejection needs a reason, sends nothing to the customer and is recorded. | Project page: **Approve and send** or **Reject**; switch user at the bottom left to try a Reviewer |
| 5. Visible outcome | The customer receives the estimate on WhatsApp, the project moves to "Quote sent", a credit is used in the Wallet, and the activity log shows who approved and when. | Project ▸ **Activity**; **Wallet** |
| 6. A second business | A second SME is a configuration change: its own business config and rate card, and for another trade its own rules file (`prompts/trades/aircon.txt`, `config/trades/aircon.json`). | See [Reuse through Orbyte](#reuse-through-orbyte) |

## Must-Haves at the Final

| Must-have | How Gesir shows it live |
| --------- | ----------------------- |
| 1. One clear SME problem | One user (a painting contractor's owner) and one chore: WhatsApp enquiry to approved quote and booked visit. |
| 2. Core automated journey | The six steps above run end to end on synthetic data, from the WhatsApp message to the recorded result. |
| 3. Accuracy and ease of learning | The same details always give the same price (deterministic engine, 607 automated tests). The dashboard uses Orbyte's layout and plain words, so an Orbyte user needs no training. |
| 4. People stay in control | Roles decide who can act; approval is enforced in the backend (a Reviewer gets 403); the activity log is written as each action happens. |
| 5. Orbyte fit and reuse | The dashboard follows Orbyte's structure (Organization, Workspace, Pending Actions, Wallet); a second business or trade is configuration, not new code. |
| 6. Business benefit and SDG | Benefit with assumptions below, tied to SDG 8.2 and 8.3. |

## Technical Expectations

- **Approval gate in the backend.** `POST /api/quotes/{id}/approve` and `/reject` check the caller's role on the server (`src/orbyte.py`, `src/server.py`). The WhatsApp message is only sent inside the approve call. A rejection writes an audit entry with the reason and the person.
- **Activity log.** Every step (estimate drafted, values edited, approved, rejected, slot offered, booking confirmed) is written to the audit table as it happens (`GET /api/audit`) and shown on each project.
- **Decision logic.** Rules handle what rules can: the next question, unit and size checks, working days, holidays, service area, prices and scheduling. AI is used where judgement on free text is needed: **Qwen2.5-7B-Instruct** for the conversation and **Qwen2.5-VL-7B-Instruct** for photos, both on RunPod. Whisper transcribes voice notes. Every value a model extracts is checked against the customer's own words before it is stored.
- **Accuracy and exceptions.** Prices come from `src/pricing.py` and the rate table, never from a model. Inspection cases (damp, mould, structural damage), customers who ask for a person, jobs the engine cannot price, and repeated unclear answers go to the owner with a clear reason.
- **Data and interfaces.** Synthetic customers and data only. The assumed Orbyte interface (roles, signed events, embedding) is documented in [`docs/ORBYTE.md`](docs/ORBYTE.md).
- **Reuse.** Business settings live in `config/` (rate card, required fields, personas, working rules, holidays). The AI rules are split into `prompts/global.txt` (every trade) and `prompts/trades/<trade>.txt` (one file per trade).
- **Engineering.** Deployed at the Live Demo link, 607 unit tests (`python -m unittest discover tests`), and steady commits on `main`.

## Impact & Evidence

**Baseline and target (Phase 1 proposal).** A painting contractor spends **10 to 15 hours a week** on WhatsApp enquiries: asking for sizes and photos, pricing, writing quotes and agreeing dates. The Phase 1 target is to cut that by **85%**.

**What Gesir removes per enquiry.** The owner no longer asks for each detail, measures the area from the customer's numbers, calculates the price, writes the quote, or proposes times. What is left is one review and one approve tap, plus replying when Gesir hands a chat over.

**How it is measured.** Every message, estimate, approval and booking is time-stamped in the event log (`/api/events`) and the audit log (`/api/audit`). Time saved per week = enquiries per week × (owner minutes per enquiry before − owner minutes per enquiry with Gesir). The final report uses these logs and the test runs (`scripts/stress_chat.py`, about 200 scenarios) as proof; the assumptions are stated there.

**Business model and cost.**
- Usage-based, suited to Orbyte's wallet: **one credit per estimate a person approves**. Nothing is charged for chats that never become an estimate.
- Running cost: the models run on RunPod serverless GPUs, billed per second and scaled to zero when idle. A typical quote uses about 10 to 30 seconds of GPU time, roughly **US$0.01 to 0.02 per quote** at RunPod's listed rates (an estimate). Hosting on Replit is a fixed monthly plan.

**Scale through Orbyte.** Any service SME that quotes over WhatsApp can use it: painters first, then aircon servicing (rules already written), plumbers, electricians, cleaners and renovators. A second business of the same trade changes only its configuration; a new trade adds its rules file and rate card.

**Privacy (PDPA).** Nothing is read before the customer agrees to a PDPA notice; "STOP" erases their data; the owner can erase a customer; only the owner's roles can see data; data is kept for the job only. See [`docs/PDPA.md`](docs/PDPA.md).

**SDG 8.2 and 8.3.** Gesir raises the productivity of micro and small businesses through technology (8.2) by removing hours of manual quoting each week, and supports their growth (8.3) by letting a small team answer more enquiries, faster, without hiring.

## Reuse through Orbyte

- **Same trade, new business:** copy `config/business_config.example.json`, set the name, owner, rate card and working rules. No code change.
- **New trade:** add `prompts/trades/<trade>.txt` (what to collect, inspection cases, trade words) and a rate card such as `config/trades/aircon.json`, then set `"trade_type"` in the business config. The aircon pricing engine is `src/pricing_aircon.py`. One chat can offer several trades (`EXTRA_TRADES`, default `aircon`): the trade is read from what the customer says, by the model when the words are not enough, and asked when it is still unclear.
- **Inside Orbyte:** a hub can call Gesir with the API key and a role, receive signed events, and embed the dashboard (`ORBYTE_ORIGIN`). See [`docs/ORBYTE.md`](docs/ORBYTE.md).

See [`docs/STATUS.md`](docs/STATUS.md) for what is built and what is still missing.

### Tech Stack

| Layer         | Technology                                              |
| ------------- | ------------------------------------------------------- |
| Frontend      | React, TypeScript and Vite (web, Orbyte-style layout), Expo React Native (mobile). Source in `frontend/` (`web/`, `mobile/`, `shared/`); the web build is served from `dashboard/` |
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
│   ├── business_config.example.json   # business, personas, required fields, Malaysian rate card
│   ├── painting_prices_malaysia_2026.csv  # the market data behind the rates
│   ├── holidays.json                  # public holidays the crew does not work
│   └── trades/aircon.json             # a second trade's rate card
├── dashboard/                         # built web dashboard served by the backend
├── docs/
│   ├── STATUS.md                      # what works and what is missing
│   ├── PRICING.md, PDPA.md            # where the rates come from; privacy and consent
│   └── ORBYTE.md                      # the assumed Orbyte interface
├── prompts/
│   ├── global.txt                     # the assistant's permanent rules, for every trade
│   └── trades/<trade>.txt             # what each trade collects (painting, aircon)
├── scripts/                           # chat.py, quote.py, build_dashboard.sh and other helpers
├── src/
│   ├── server.py                      # FastAPI app: WhatsApp webhook, dashboard API, login, static site
│   ├── service.py                     # one incoming message -> replies; quotes, bookings, takeover
│   ├── assistant.py, flow.py          # the conversation: prefill, corrections, steps around the model
│   ├── prompt.py, validation.py,      # prompt building, grounding and screening of model output
│   │   grounding.py, guard.py
│   ├── pricing.py                     # deterministic estimate and working-hours engine
│   ├── scheduling.py                  # slot suggestions, area clustering, bookings
│   ├── calendar_scheduler.py          # the team's calendar rules (working hours)
│   ├── whatsapp.py, events.py         # WhatsApp sending, media download, webhook parsing
│   ├── whatsapp_calling.py            # call hand-off to LiveKit
│   ├── transcribe.py, vision.py       # voice notes (Whisper) and photo assessment
│   ├── i18n.py, persona.py            # English and Malay texts, personas
│   ├── store.py                       # SQLite and PostgreSQL storage
│   └── views.py, pdf.py, webauth.py   # dashboard shapes, estimate PDF, dashboard login
├── voice_worker/                      # LiveKit voice agent that answers WhatsApp calls (own process)
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
| `INCOMING_API_KEY` | key for the dashboard API and scripts (`x-api-key`) |
| `SESSION_SECRET` | signs the dashboard's session cookie (accounts are created at `/signup`) |
| `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_APP_SECRET` | receiving WhatsApp webhooks |
| `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID` | sending messages, downloading photos and voice notes |
| `DATABASE_URL` | PostgreSQL (Replit sets it); without it a local SQLite file is used |
| `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `WHATSAPP_LIVEKIT_AGENT_NAME` | WhatsApp calls (see `voice_worker/README.md`) |
| `CORS_ORIGINS`, `STT_MODEL_SIZE`, `MESSAGE_WINDOW_SECONDS` | optional |

### Option 1 — Run on Replit (recommended)

1. Open the [Replit Project](https://replit.com/@AzerHamdaoui/Bridge-app), or import this repository with **Create Repl → Import from GitHub**.
2. Add the secrets above. Add a PostgreSQL database in the Replit **Database** tool.
3. Dependencies come from `pyproject.toml` (Replit uses uv). Click **Run**, or publish with Replit **Deployments** (Reserved VM).
4. In the Meta developer dashboard, set the WhatsApp callback URL to `https://<your-app>.replit.app/webhook` with your verify token, and subscribe to `messages` (and `calls` for calls).
5. Open `https://<your-app>.replit.app/app`, create an account at `/signup`.

### Option 2 — Run locally

```bash
git clone https://github.com/Azer884/Bridge-app.git
cd Bridge-app
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
pip install httpx                        # only needed to run the tests
cp .env.example .env            # then fill in your values
uvicorn src.server:create_app --factory --port 8000
```

Without `DATABASE_URL` the app keeps its data in `data/bridge.db`. `python scripts/run_local_demo.py` runs the app with a fake WhatsApp sender (sign up at `/signup`).

To rebuild the web dashboard:

```bash
cd frontend/web
npm install
VITE_USE_MOCK=false VITE_BOOKINGS_LIVE=true npx vite build --outDir ../../dashboard --emptyOutDir
```

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

📄 Proof of use: [`submission/SDC2026_HRISSA_Replit_POU.pdf`](submission/SDC2026_HRISSA_Replit_POU.pdf)

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

📄 Proof of use: [`submission/SDC2026_HRISSA_Runpod_POU.pdf`](submission/SDC2026_HRISSA_Runpod_POU.pdf)

---

## Challenges & Learnings

- **Trusting a small model.** A 7B model sometimes invented values, asked two questions, or wrote plain text instead of the required format. We moved every decision into code: the backend picks the next question, checks each extracted value against the customer's own words, reads simple answers itself, retries and then falls back to a safe template.
- **Real customers are messy.** Chats showed people changing their mind, sending several messages at once, guessing sizes, writing in Malay or Manglish and sending locations. Each case became a rule with a regression test.
- **Cold starts and hosting limits.** GPU workers take minutes to wake and Replit deployments lose local files on every republish. We added graceful waiting messages, a status view, and PostgreSQL.
- **Debugging without logs.** Production logs were not readable, so the app records its own event trail (`/api/events`), which found the expired WhatsApp token and a PyAV version clash that broke voice notes.
- **Prices must be explainable.** The estimate is deterministic, uses Malaysian market rates, is always labelled as an estimate (customers can give wrong sizes), and the owner can correct any value before it is sent.

## Future Improvements

- [ ] Confirm voice notes and WhatsApp calls end to end in the live demo
- [x] Exclude weekends and Malaysian public holidays (`config/holidays.json`)
- [x] Painting and aircon in the same chat (read from context, or asked); not yet tried with the live model
- [ ] WhatsApp message templates, so estimates and slot offers work after the 24-hour window
- [ ] Rate card and working-hours editor in the dashboard, with the SME's real prices
- [ ] Owner notifications (WhatsApp or push) for new quotes and messages that need a person
- [ ] Customer reschedule and cancel, and day-before reminders
- [x] Privacy consent (PDPA notice before any data is read) and data deletion (STOP, owner erase). See [`docs/PDPA.md`](docs/PDPA.md)
- [ ] Per-user logins

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

- [x] Team name, domain (Domain 1 / Domain 2) and SDG track filled in
- [x] Slide deck link added
- [ ] Demo video link updated for the Final
- [x] Replit used, with proof of use in `submission/`
- [x] RunPod used, with proof of use in `submission/`
- [x] Technical & Tools Declaration added to `submission/`
- [x] Final report (`SDC2026_HRISSA_Final.pdf`) added to `submission/`
- [x] "How to Run" steps verified (clean virtualenv, `pip install -r requirements.txt`, tests pass)
- [x] No API keys or secrets committed to the repository

## License

This project is licensed under the [Apache License 2.0](LICENSE).
