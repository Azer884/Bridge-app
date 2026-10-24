# Gesir dashboard

Gesir is an AI middleman: linked to your WhatsApp number, it talks to customers on your behalf and asks your permission before anything is sent. This is the SME dashboard. For any business that talks to customers about jobs: plumbers, painters, electricians, builders. Web (Vite, React, TypeScript, GSAP) and mobile (Expo, React Native).

```
shared/   api.ts, types.ts, mock.ts, format.ts  (one typed client used by both apps)
web/      landing page + dashboard
mobile/   Expo app
brand/    "Wet edge" poster and its design philosophy
```

Both apps follow the system theme and have a light/dark switch at the top right (saved per device).

## Run

```bash
cd web && npm install && npm run dev
```

```bash
cd mobile && npm install && npx expo start
```

Both start in **sample-data mode** (`*_USE_MOCK=true`), so every screen works without the backend.
Sample data includes a cold-start "waking up" state and one approve that fails once with a 502 so you can see the retry.

## Link the backend

Web: copy `web/.env.example` to `web/.env`, set `VITE_USE_MOCK=false`, `API_URL` and `API_KEY`.
The Vite proxy adds `x-api-key` server-side, so the key never ships in the browser bundle and no CORS is needed in dev.
For production, keep the dashboard behind a login with a small proxy, or add real auth on the backend.

Mobile: copy `mobile/.env.example` to `mobile/.env`, set `EXPO_PUBLIC_USE_MOCK=false`, URL and key.
`EXPO_PUBLIC_` values are bundled into the app, so use it for internal builds only until there is real auth.

## Backend gaps the UI already handles

- Google Calendar: web has two-way view and copy-out. Set `VITE_GOOGLE_CLIENT_ID` (OAuth Web client, Calendar API on, add your origin to Authorized JavaScript origins). With no id and mock mode on it runs a demo. Mobile opens a pre-filled Google Calendar event per booking (no sign-in setup). For production move the sync to the backend so tokens stay server-side.
- WhatsApp linking: `/app/connect` and the mobile WhatsApp tab use sample data. Needs `GET /api/whatsapp/status`, `POST /api/whatsapp/link`, `DELETE /api/whatsapp/link` on the backend.
- Bookings: calendar uses in-memory sample data. Set `VITE_BOOKINGS_LIVE=true` / `EXPO_PUBLIC_BOOKINGS_LIVE=true` once `/api/bookings` exists (shape in `shared/api.ts`).
- `/api/events` and `/api/models/health` response shapes are not documented, so `shared/api.ts` normalises them loosely. Adjust `normalizeEvent` and `normalizeHealth` after checking `/docs`.
- No push for new quotes: both apps poll `GET /api/quotes` (web 15 to 20 s, mobile 15 to 20 s, with a haptic buzz on a new draft).




## Review features and the backend contract

The quote screen, pipeline and calendar suggestions are front end only. They call these endpoints (paths are the assumed contract; change them in one place, the `api` object in `shared/api.ts`). In mock mode, `shared/mock-detail.ts` stands in for all of them.

| Method | Path | Returns |
|---|---|---|
| GET | `/api/quotes/{id}` | `QuoteDetail`: job, quote, `stage`, `params` (schema, ai, current, confidence), `chat`, `photos`, `audit`, `duration_hours`, `locked` |
| POST | `/api/quotes/{id}/recalculate` body `{params}` | `Recalculation`: `quote` (with `labor_hours`) and `duration_hours`. The UI never computes prices |
| PUT | `/api/quotes/{id}/params` body `{params}` | saves overrides, appends audit entries |
| POST | `/api/quotes/{id}/pdf` body `{params}` | `PdfPreview`: `url` (or `base64`), `filename`, `generated_at` |
| GET | `/api/pipeline` | `PipelineRow[]` (quote plus `stage`) |
| GET | `/api/audit?limit=` | recent `AuditEntry` with `user_id` and `customer` |
| POST | `/api/quotes/{id}/slots` body `{busy}` | `Slot[]` (`start`, `end`, `score`, `reason`) |

Types live in `shared/types.ts`. Approve still uses `POST /api/quotes/{user_id}/approve`.

## Web and mobile parity

Both apps have the same features: quote review (edit what Gesir read, live price, chat and photos, PDF preview, approve), pipeline (list and board, recent activity), calendar (month, week, day, suggested times, double-booking guard), WhatsApp linking with country codes, personas, status, and light, dark or system appearance.

Differences that come from the platform:
- Google Calendar: the web app can connect and sync (needs `VITE_GOOGLE_CLIENT_ID`). The mobile app opens a pre-filled Google Calendar event per booking.
- PDF: the web app shows it in a frame. On a phone the system viewer opens the file the server returns.
- The mobile app uses iOS patterns: tab bar, large titles, inset grouped lists, page sheets, haptics. Photos from the backend must be PNG or JPEG for the phone to draw them (SVG sample photos only show on the web).
