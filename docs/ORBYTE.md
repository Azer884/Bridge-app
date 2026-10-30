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

## Not done yet

- A different trade (not painting): pricing, schema and prompts are not config-only yet. A second business of the same trade is a config change (`config/business_config.second.example.json`).
- The real Orbyte site has no public API or embed settings, so the mock hub (`scripts/mock_orbyte.py`) stays as the demo stand-in until Orbyte publishes one.
