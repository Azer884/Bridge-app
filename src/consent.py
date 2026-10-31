"""Consent under Malaysia's Personal Data Protection Act 2010 (PDPA).

Before Gesir reads a customer's job details, photos or voice notes it tells them what it keeps, why, who sees it and how to
withdraw, and waits for a "1". A customer can withdraw any time by typing STOP, which erases their chat, bookings and log.
The notice texts are in i18n.py (consent_*). Switch it off for a business with {"privacy": {"require_consent": false}}.
"""
import re

AGREE = {"1", "agree", "i agree", "yes", "y", "ya", "ye", "setuju", "saya setuju", "ok", "okay", "boleh", "sure"}
DECLINE = {"2", "no", "n", "tidak", "tak", "decline", "disagree", "i disagree", "tak setuju", "tidak setuju", "taknak"}
WITHDRAW = {"stop", "withdraw", "unsubscribe", "delete my data", "erase my data", "remove my data", "opt out", "stop sending",
            "padam data saya", "henti", "berhenti", "tarik balik"}
MAX_ASKS = 3


def clean(text):
    return re.sub(r"[^\w\s]", "", (text or "").lower()).strip()


def agrees(text):
    return clean(text) in AGREE


def declines(text):
    return clean(text) in DECLINE


def withdraws(text):
    """Only a message that is nothing but the request: "stop, I meant 4m" is a correction, not a withdrawal."""
    return clean(text) in WITHDRAW


_NOUN = (r"(?:address|name|phone|number|contact|details?|data|info|information|photos?|pictures?|images?|messages?|"
         r"voice|alamat|nama|nombor|maklumat|gambar|mesej)")
# "you can't record my address", "don't keep my details": an objection to the data being held, said in ordinary words
_OBJECTIONS = [
    re.compile(r"\byou\s+(?:can'?t|cannot|can\s+not|may\s+not|must\s+not|shouldn'?t|should\s+not|are\s+not\s+allowed\s+to|"
               r"aren'?t\s+allowed\s+to|have\s+no\s+right\s+to)\s+(?:\w+\s+){0,2}?(?:record|have|keep|store|save|use|collect|process|"
               r"share|read|take|hold|track)\b(?:\W+\w+){0,5}?\W+" + _NOUN + r"\b", re.I),
    re.compile(r"\b(?:don'?t|do\s+not|dont|never|stop|please\s+don'?t)\s+(?:you\s+)?(?:record|keep|store|save|use|collect|process|"
               r"share|track)(?:ing)?\b(?:\W+\w+){0,4}?\W+" + _NOUN + r"\b", re.I),
    re.compile(r"\bi\s+(?:do\s*n'?t|do\s+not|dont|won'?t|will\s+not)\s+(?:consent|agree|give\s+(?:you\s+)?(?:my\s+)?permission)\b", re.I),
    re.compile(r"\b(?:i\s+)?(?:withdraw|revoke|take\s+back)\s+(?:my\s+)?(?:consent|permission|agreement)\b", re.I),
    # "nvm dont have my agreement", "you don't have my consent", "no consent", "I never agreed", "I didn't agree"
    re.compile(r"\b(?:you\s+)?(?:do\s*n'?t|do\s+not|dont|don'?t)\s+(?:have|got)\s+(?:my\s+)?(?:agreement|consent|permission)\b", re.I),
    re.compile(r"\bno\s+(?:consent|permission|agreement)\b", re.I),
    re.compile(r"\bi\s+(?:never|did\s*n'?t|did\s+not|didnt|have\s*n'?t|haven'?t)\s+(?:agree|agreed|consent|consented|give\s+permission)\b", re.I),
    re.compile(r"\b(?:tak|tidak)\s+(?:beri|bagi)\s+(?:kebenaran|persetujuan)\b", re.I),
    re.compile(r"\b(?:jangan|tak\s+boleh|tidak\s+boleh|dilarang)\s+(?:\w+\s+){0,2}?(?:simpan|rekod|guna|ambil|kumpul|proses|kongsi)\b"
               r"(?:\W+\w+){0,4}?\W+" + _NOUN + r"\b", re.I),
    re.compile(r"\b(?:tarik\s+balik|tidak\s+setuju|tak\s+setuju)\b.*\b(?:persetujuan|data|maklumat)\b", re.I),
]


def objects(text):
    """True when the customer says in their own words that the data must not be recorded or kept. That is a withdrawal of
    consent: nothing more is processed until they say what they want. A plain "I don't have my number" is not one."""
    return any(p.search(text or "") for p in _OBJECTIONS)


def required(config):
    return bool((config.get("privacy") or {}).get("require_consent", False))
