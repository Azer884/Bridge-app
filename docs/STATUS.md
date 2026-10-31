# Where the project stands

## Works today
- WhatsApp assistant in English and Bahasa Malaysia (detects the language, switches on request), with personas, a fixed
  conversation order (job details, then address, then contact, recap, confirm), corrections ("nvm its 4m"), messages
  sent in a burst read as one, "start over", repeat customers, shared locations, photos (with captions) and voice notes.
- Estimates from a deterministic Malaysian rate card: breakdown for the owner only, customer gets the total, the time the job
  takes and a clear "estimate only" note. The owner edits the values, approves, and later sends the final price.
- Booking rules: Monday to Friday, 9 am to 6 pm with lunch from 1 to 2 pm. Weekends, public holidays (`config/holidays.json`),
  times like "3 am" and addresses outside Malaysia are refused in the chat and in the calendar.
- Calendar: area-aware slot suggestions that respect what the customer asked for ("Monday evening"), travel gaps, no double
  booking, an offer to the customer that they confirm on WhatsApp. The dashboard books real slots through `/api/bookings`;
  a job that runs through lunch is shown in two parts.
- Dashboard (web) in an Orbyte-style layout, hosted on the same Replit app behind a sign-up and sign-in (name, business, email, password, trade): Dashboard (Pending Actions),
  Clients, Projects (each opens the quote: review, edit, recalculate, approve or reject, PDF, chat, activity), Users,
  Wallet, Organization settings (WhatsApp, personas, model status) and the Job Calendar. See `docs/ORBYTE.md`.
- Roles: Company Admin and Approver may approve or reject, a Reviewer may only read; the server checks the role.
- AI rules split into `prompts/global.txt` and one file per trade (`prompts/trades/painting.txt`, `aircon.txt`).
- PostgreSQL storage, an audit trail per job, an events trail for debugging.

## Google Calendar
Not part of the product for now: the dashboard no longer shows it. The old browser sync code (`frontend/web/src/google.ts`) and
the server class in `src/calendar_scheduler.py` are kept for later but are not used.

## What is missing
1. **WhatsApp production setup.** The bot can only reply freely within 24 hours of the customer's last message. Estimates and
   slot offers sent later need Meta-approved message templates. Also needed: a real business number, business verification,
   the Meta app set to Live, and a permanent system-user token instead of the temporary one.
2. **Calls.** `voice_worker/` answers WhatsApp calls through LiveKit (see `voice_worker/README.md`). It must run on a
   machine of ours, and calls have not been tested end to end on the Meta test number.
3. **Voice notes are untested on the live server.** `GET /api/voice/health` says whether the model loaded and why not.
4. **Owner login.** Anyone can sign up and sign in with email and password (stored as scrypt hashes). The trade chosen at sign-up is only recorded: painting and aircon both work for every account. The people and roles in Users are still simulated ("Act as"), not tied to accounts. No email verification or password reset.
   Rotate `INCOMING_API_KEY` (it was pasted in chats, and the Android app contains it).
5. **Google Calendar** is not used for now (see above). Weekends and public holidays are excluded (`config/holidays.json`).
6. **Rate card and settings editor.** Rates, crew size, working hours and services live in `config/business_config.example.json`;
   the SME cannot edit them from the dashboard. The rates are demo values until the real company supplies its own.
7. **Customer-side scheduling.** The customer cannot reschedule or cancel on their own; a day-before reminder is not sent.
8. **Estimate PDF is a preview only**; it is not sent to the customer as a WhatsApp document.
9. **Alerts for the owner.** The mobile app receives Expo push notifications; the web dashboard only shows new quotes and
   "needs a person" messages when it is open (it polls).
10. **Privacy.** A PDPA consent notice before anything is read (spoken on calls, answered by "yes" or "no"), STOP to erase, and owner erasure exist (see `docs/PDPA.md`). Still missing: automatic expiry, a customer data export.
11. **Scope.** Only interior walls and ceilings are priced; trim, doors and exterior work go to a person.
12. **Operations.** No automated alerting, no database backup routine, no automated frontend tests, no CI.
13. **Orbyte.** The dashboard follows Orbyte's layout and the hub interface is assumed (`docs/ORBYTE.md`); there is no live
   Orbyte API to connect to.
14. **Second trade in the chat.** One chat serves painting and aircon (`EXTRA_TRADES`, default `aircon`; `src/trades.py`). The
   trade is read from the customer's words, then by the model, and asked when still unclear ("painting or aircon servicing?").
   Aircon asks for the service, the number of units, the horsepower, any problem and the date, then prices from
   `config/trades/aircon.json`; the dashboard form shows units, service, horsepower and condition. Aircon photos go to the vision model with an aircon prompt
   (`src/vision.py`): it names the unit type and what it sees (dirty filter, water stains, ice...) from fixed lists, never a
   number. Not done: no aircon-specific FAQ answers, and the second trade and its photo prompt have not been tried with the
   live model.

## Stress testing the chat

`scripts/stress_chat.py` sends 208 scenarios (about 600 messages: vague sizes, mixed units, Malay and Manglish,
changes of mind, side questions, refusals, odd services, injection attempts, dates and colours) to the live model through
the real service and writes every reply to a file. It costs roughly one US cent per 10 model calls on a 24 GB RunPod
GPU; a full run makes about 250 calls. Read the output file for stiff, repeated or wrong replies, fix them, and rerun
only the scenario groups that changed (for example `time,colour`). Regression tests for what it found are in
`tests/test_stress_fixes.py`.

Known gaps it did not fix: areas given as square metres or square feet are not turned into room sizes, "steps" or
"paces" are not read as a unit, and a second room mentioned in the same message is ignored until the first is done.
