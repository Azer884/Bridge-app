# Where the project stands

## Works today
- WhatsApp assistant in English and Bahasa Malaysia (detects the language, switches on request), with personas, a fixed
  conversation order (job details, then address, then contact, recap, confirm), corrections ("nvm its 4m"), messages
  sent in a burst read as one, "start over", repeat customers, shared locations, photos (with captions) and voice notes.
- Estimates from a deterministic Malaysian rate card: breakdown for the owner only, customer gets the total, the time the job
  takes and a clear "estimate only" note. The owner edits the values, approves, and later sends the final price.
- Calendar: area-aware slot suggestions that respect what the customer asked for ("Monday evening"), travel gaps, no double
  booking, an offer to the customer that they confirm on WhatsApp.
- Dashboard (web) hosted on the same Replit app behind a password: quotes, review screen (edit, recalculate, PDF), pipeline,
  calendar, personas, status, and writing to a customer in the assistant's place.
- PostgreSQL storage, an audit trail per job, an events trail for debugging.

## Link Google Calendar
The web dashboard already syncs with Google in the browser; it only needs a Google OAuth client id.
1. Google Cloud console: create a project, then APIs and Services, Library, enable **Google Calendar API**.
2. OAuth consent screen: type External, add your own Google account under Test users (testing mode is fine for the demo).
3. Credentials, Create credentials, **OAuth client ID**, type **Web application**. Under Authorized JavaScript origins add
   `https://gesir-ai.replit.app` and `http://localhost:5173`. Copy the client id (it is public, not a secret).
4. Put `VITE_GOOGLE_CLIENT_ID=<the id>` in `frontend/web/.env`, run `scripts/build_dashboard.sh <path to frontend/web>`,
   commit `dashboard/`, republish. The id is baked into the build, which is why a rebuild is needed.
5. Dashboard, Calendar, Connect Google. Busy events from Google are sent with every slot request so they are never offered.
Limits: it syncs only while the dashboard is open in a browser. The server-side route (the team's `GoogleCalendar` class
in `src/calendar_scheduler.py`) needs a server-held OAuth token and is not connected yet.

## What is missing
1. **WhatsApp production setup.** The bot can only reply freely within 24 hours of the customer's last message. Estimates and
   slot offers sent later need Meta-approved message templates. Also needed: a real business number, business verification,
   the Meta app set to Live, and a permanent system-user token instead of the temporary one.
2. **Calls.** The voice-agent branch is not connected (planned).
3. **Voice notes are untested on the live server.** `GET /api/voice/health` says whether the model loaded and why not.
4. **Owner login.** One shared dashboard password; no per-person accounts or roles. Rotate `INCOMING_API_KEY` (it was pasted in chats).
5. **Google Calendar on the server** (see above), and Malaysian public holidays are not excluded from the calendar.
6. **Rate card and settings editor.** Rates, crew size, working hours and services live in `config/business_config.example.json`;
   the SME cannot edit them from the dashboard. The rates are demo values until the real company supplies its own.
7. **Customer-side scheduling.** The customer cannot reschedule or cancel on their own; a day-before reminder is not sent.
8. **Estimate PDF is a preview only**; it is not sent to the customer as a WhatsApp document.
9. **Alerts for the owner.** New quotes and "needs a person" messages are only visible by opening the dashboard (it polls).
   A WhatsApp or push notification to the owner would close that gap.
10. **Privacy.** No consent notice, data export or deletion, or retention rule yet (Malaysia's PDPA applies).
11. **Scope.** Only interior walls and ceilings are priced; trim, doors and exterior work go to a person.
12. **Operations.** No automated alerting, no database backup routine, no automated frontend tests, no CI.
13. **Hackathon platform.** Orbyte is not integrated (put aside on purpose).

## Stress testing the chat

`scripts/stress_chat.py` sends 208 scenarios (about 600 messages: vague sizes, mixed units, Malay and Manglish,
changes of mind, side questions, refusals, odd services, injection attempts, dates and colours) to the live model through
the real service and writes every reply to a file. It costs roughly one US cent per 10 model calls on a 24 GB RunPod
GPU; a full run makes about 250 calls. Read the output file for stiff, repeated or wrong replies, fix them, and rerun
only the scenario groups that changed (for example `time,colour`). Regression tests for what it found are in
`tests/test_stress_fixes.py`.

Known gaps it did not fix: areas given as square metres or square feet are not turned into room sizes, "steps" or
"paces" are not read as a unit, and a second room mentioned in the same message is ignored until the first is done.
