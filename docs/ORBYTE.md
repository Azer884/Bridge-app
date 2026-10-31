# Orbyte link (assumed interface)

Orbyte has no public API or sandbox, so this is the interface Gesir assumes. It is what a hub like Orbyte would call, and
it is implemented and tested in this repository. The Gesir dashboard itself has the Orbyte layout, so there is no separate hub app.

## Mapping

| Orbyte | Gesir |
| ------ | ----- |
| Organization (tenant) | One business: its own config (`BUSINESS_CONFIG`) and database |
| Client | Customer (`GET /api/customers`) |
| Project | A quote or job (`GET /api/quotes?status=...`) |
| Pending action, Approve queue | Quotes in `pending_approval` and `needs_inspection` |
| Approver / Admin role | May approve or reject an estimate |
| Reviewer role | May read, may not approve or reject |
| Wallet credits | One credit per approved estimate (charged by the hub) |

## Requests from the hub

Send the shared API key in `x-api-key`, plus `x-orbyte-role` (`admin`, `approver` or `reviewer`) and `x-orbyte-user`
(a display name). A missing role means `admin`; an unknown role is treated as `reviewer`. The dashboard's own login is `admin`.

| Call | Who may call |
| ---- | ------------ |
| `GET /api/quotes?status=`, `GET /api/quotes/{id}`, `GET /api/customers`, `GET /api/audit` | any role |
| `POST /api/quotes/{id}/approve` | admin, approver |
| `POST /api/quotes/{id}/reject` with `{"reason": "..."}` (3 to 200 characters) | admin, approver |

The role is checked in the backend. A refused call returns 403 and sends nothing to the customer.
Reject sends nothing to the customer, writes an audit entry with the reason and the person, and removes the job from the
queue. Editing the job values re-prices it and puts it back in the queue. Approve and reject entries in the audit log name
who acted and in which role.

## Events from Gesir to the hub

Set `ORBYTE_WEBHOOK_URL` and `ORBYTE_SHARED_SECRET`. Each event is a JSON POST with the header
`x-orbyte-signature: sha256=<HMAC-SHA256 of the raw body, keyed with the shared secret>`.

| Event | When |
| ----- | ---- |
| `quote.pending_approval` | A new estimate, an inspection request, or a changed job needs a decision |
| `quote.approved` | An estimate was approved and sent to the customer |
| `quote.rejected` | An estimate was rejected, with the reason |
| `quote.final` | The final price was confirmed |

Events are written to the store before they are sent (setting `orbyte_outbox`, so PostgreSQL on Replit keeps them) and
removed once the hub accepts them. Delivery runs in a background thread with retries after 0, 2 and 10 seconds. If the hub
stays down the event stays queued and goes out on the next start; the failure is logged as an `orbyte_send_failed` event.
The newest 200 queued events are kept.

## Embedding the dashboard in the hub

Set `ORBYTE_ORIGIN` to the hub's address (for example `https://hub.example.com`). The dashboard then sends
`Content-Security-Policy: frame-ancestors 'self' <origin>`, so only that site can frame it, and over https the login
cookie becomes `SameSite=None` so it is sent inside the frame. Over plain http the cookie stays `SameSite=Lax`, which is
enough for the local mock hub because localhost on two ports is the same site.

## The Orbyte-style dashboard (served by Gesir at `/app`)

Gesir's own dashboard follows the real Orbyte as seen in a signed-in account (October 2026). It uses no Orbyte code, logo or
images, and it keeps the Gesir name and logo. There is no second app: everything runs in the one Gesir deployment.

| Screen | Copied from the real Orbyte | Assumed (Orbyte does not publish it) |
| ------ | --------------------------- | ------------------------------------ |
| Layout, organization box, menu search, signed-in user at the bottom | Yes | |
| Dashboard with Pending Actions and All, Submit, Review, Approve tabs | Yes | Gesir estimates appear as Approve items; customers who need a person appear under Review |
| Organization: Clients, Projects | Yes | Customers become Clients and quotes become Projects |
| Users (Role, Approver, Reviewer) | Yes | Company Admin and Approver may approve; Reviewer and Member may only read |
| Wallet (balance, Transactions) | Yes | One credit is used per approved estimate (`GET /api/wallet`) |
| Organization Settings with Integrations | Yes | A "Gesir" row and the WhatsApp number with Unlink; Personas and Status tabs |
| Projects ▸ a project | | The Gesir quote page: what the AI read, the price, approve or reject, chat and photos, PDF, activity |
| Workspace: Job Calendar | | Month view laid out like Orbyte's Leave Calendar (Monday to Friday, holidays as pills); week and day hour grids |

Choosing a person at the bottom left ("Act as") sends their role with every request (`x-orbyte-role`, `x-orbyte-user`). The
signed-in owner may pick any role, and the server enforces it: a Reviewer gets 403 on approve and reject. Users and credits are
simulated and kept in the store (`GET /api/hub/users`, `GET /api/wallet`). Not copied, because they would be invented: the Leave
Calendar itself, leave requests, tasks, e-sign, top-up payments, Email Broadcast and reports. They show as greyed menu items.
The users are the team members acting in the three roles (Azer Hamdaoui, Omar Bouhlel, Tarek Ben Slimen).

## A real hub

A real Orbyte hub can still call Gesir with the API key and the role headers (the table above), receive the signed events, and embed
the dashboard with `ORBYTE_ORIGIN`. Set `ORBYTE_WEBHOOK_URL` and `ORBYTE_SHARED_SECRET` on the Gesir app for the events. Approving
sends a real WhatsApp message, so use test customers only.

## Not done yet

- A different trade (not painting): its AI rules (`prompts/trades/<trade>.txt`), fields, rate card and pricing engine are added, then listed in `EXTRA_TRADES`. Aircon is done this way (`src/trades.py`, `src/pricing_aircon.py`). A second business of the same trade is a config change (`config/business_config.second.example.json`).
- The real Orbyte site has no public API or embed settings, so the Orbyte-style dashboard in Gesir stays as the demo stand-in until Orbyte publishes one.
