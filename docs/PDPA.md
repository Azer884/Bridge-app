# Personal data and Malaysia's PDPA 2010

Gesir.AI handles customers' names, phone numbers, addresses, photos of their homes and voice notes, so the Personal Data
Protection Act 2010 applies. This is how the product handles its principles. It is not legal advice; a real deployment
needs a review by the business and its adviser.

## Consent in the chat

On a customer's first message nothing is read, saved or sent to a model. They get this notice instead:

> Under Malaysia's PDPA 2010, do you consent to {business} (using Gesir.AI) processing your job details, photos, voice
> notes and phone number to prepare this quote? Only {owner} sees them, we keep them only for this job, and you can
> withdraw any time by typing STOP, which erases them. (Reply 1 to agree, 2 to decline)

The same notice exists in Bahasa Malaysia (`src/i18n.py`, keys `consent_*`). The language follows the customer's first message.

| Customer sends | What happens |
| -------------- | ------------ |
| `1`, yes, ya, setuju | Consent and its time are recorded in the log. The first message, held unread until now, is processed and the chat goes on. |
| `2`, no, tidak | Nothing is processed and the held message is dropped. They can reply `1` later. |
| Anything else, a photo or a voice note | The notice is repeated (3 times at most, then silence). The photo or voice note is not opened. |
| `STOP`, "delete my data", "padam data saya" (the whole message) | Their chat, photos, bookings, log and message ids are erased and they get a confirmation. |

"Stop, I meant 4 m" is a correction, not a withdrawal: only a message that is nothing but the request erases data.

**Withdrawal in the customer's own words.** A customer does not have to type STOP. "You can't record my address", "nvm dont have
my agreement", or a long message saying they would rather you did not keep their details (in English, Malay or another language)
pauses everything. Fixed phrases catch the common ones (`src/consent.py`), and for longer or unusual messages the model reads what
the customer means (`src/intent.py`) and returns one label. Code decides what happens: processing stops, the owner is flagged, and the
customer is told to reply STOP to erase everything or 1 to carry on. The model never writes a reply and never erases anything.
Only messages that contain a related word, or are long, are sent to the model. Set `AI_INTENTS=0` to turn the model reading off.
The same reading recognises a cancel and a restart said in other words, but only when the model is at least 85% sure.

**Calls.** A caller gets the same notice, spoken (`consent_notice_voice`): what is recorded, who sees it, and that they can say
"stop" to have it erased. Nothing they say is read or saved until they say "yes" (or "ya", "setuju"); "no" declines, and any
other answer is asked again by voice (`consent_again_voice`) up to three times. The first thing the caller said is kept
unread and replayed once they agree. The agent's greeting still says the call is recorded.

## Principles

| PDPA principle | In Gesir |
| -------------- | -------- |
| General, notice and choice | The notice above, shown before anything is processed. It names the purpose, the data, who sees it and how to withdraw. |
| Disclosure | Only the business's own users see a customer's data: admins and approvers can act on it, reviewers can only read it. Quotes go to the customer on WhatsApp. Models run on RunPod, which receives the message text, photos and voice notes only while a reply is prepared. Call audio goes through LiveKit to Deepgram (speech to text) and Cartesia (text to speech). Owner notifications go through Expo. |
| Security | Dashboard login, API key, signed webhooks, role checks in the backend, a tamper-evident log (each entry carries a hash of the one before). |
| Retention | Kept for the job only. The owner can erase a customer (`DELETE /api/customers/{id}/data`, admin or approver). There is no automatic expiry yet. |
| Data integrity and access | The owner corrects values in the dashboard and every change is logged. A customer can ask the owner for their data. There is no self-service export yet. |
| Cross-border | RunPod and WhatsApp (Meta) servers may be outside Malaysia. The notice does not say so yet; add it before real use. |

## Settings

`config/business_config*.json`, block `privacy`: `require_consent` (true by default; a business can set false), `notice_version`
(written to the log with each consent). The customer list in the API (`consent`: none, pending, granted or declined)
shows the state per customer.

## Not done yet

- Automatic deletion after a retention period.
- A data export for a customer.
- Naming cross-border transfers in the notice.
- A consent column in the dashboard (the API sends it already).
