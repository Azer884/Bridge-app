# Orbyte link (assumed interface)

Orbyte has no public API or sandbox, so this is the interface Gesir assumes. It is what a hub like Orbyte would call, and
it is implemented and tested in this repository. `scripts/mock_orbyte.py` plays the hub on a developer's machine.

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

## The mock hub (`scripts/mock_orbyte.py`)

It follows the real Orbyte as seen in a signed-in account (October 2026) and shows only what Orbyte has. It uses no Orbyte code,
logo or images, and is labelled "simulated".

| Screen | Copied from the real Orbyte | Assumed (Orbyte does not publish it) |
| ------ | --------------------------- | ------------------------------------ |
| Layout, organization switcher, menu search, signed-in user at the bottom | Yes | |
| Dashboard, Pending Actions with All, Submit, Review, Approve tabs | Yes | Gesir estimates appear as Approve items |
| Clients, Project List (Search, Status, Source, Sync all) | Yes | Customers become Clients and quotes become Projects with Source "Gesir" |
| Users, Settings & Notifications (Role, Approver, Reviewer, Notification recipients, Status) | Yes | Company Admin and Approver may approve; Reviewer and Member may only read |
| Wallet (balance, Recent activity, Transactions) | Yes | One credit is used per approved estimate |
| Organization Settings, Integrations | Tab exists (Qwen key, Documenso) | A "Gesir" card and the signed events it sends |
| "Gesir Quotes" item and "Open in Gesir" | | The module opens in a frame |

Not copied, because they would be invented: the Leave Calendar (it is for leave and public holidays, so Gesir jobs do not belong in it; the job calendar is in the Gesir module itself), leave requests, tasks, e-sign, top-up payments, Email Broadcast, reports. They show
as greyed menu items or are left out. Users (Azer, Aisha, Mei) and their roles are simulated; the hub, not the browser, decides
which role goes to the module.

## Hosting the hub with a hosted Gesir (Replit)

The local hub cannot work with a hosted Gesir as it is: the hosted app cannot send webhooks to `localhost`, and a login cookie from
another site is not sent inside a frame. Run the hub on its own https address instead:

1. Create a second Replit app from the same repository. Both apps use the same `.replit`, whose run command is `python scripts/start.py`. In the hub app only, add the secret `ORBYTE_HUB` = `1`: that makes `start.py` run the hub instead of Gesir. Never edit `.replit` or run Sync from one app to fix the other.
2. Secrets on the hub: `HUB_TENANTS` (for example `[{"id":"hrissa","name":"Hrissa","url":"https://gesir-ai.replit.app"}]`),
   `INCOMING_API_KEY` (the Gesir app's key) and `ORBYTE_SHARED_SECRET` (any long random string).
3. Secrets on the Gesir app: `ORBYTE_ORIGIN` (the hub's https address), `ORBYTE_SHARED_SECRET` (the same string) and
   `ORBYTE_WEBHOOK_URL` (`https://<hub address>/hub/webhook/hrissa`, the last part is the organization id). Republish it.
4. Open the hub, choose Gesir Quotes, and sign in to the dashboard once inside the frame.

Warning: approving in the hub sends a real WhatsApp message through the hosted Gesir. Use it with the test customers only,
or point `HUB_TENANTS` at a separate demo deployment of Gesir with seeded data.
The wallet and the list of events are kept in memory, so they reset when the hub restarts.

## Not done yet

- A different trade (not painting): pricing, schema and prompts are not config-only yet. A second business of the same trade is a config change (`config/business_config.second.example.json`).
- The real Orbyte site has no public API or embed settings, so the mock hub (`scripts/mock_orbyte.py`) stays as the demo stand-in until Orbyte publishes one.
