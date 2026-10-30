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


def required(config):
    return bool((config.get("privacy") or {}).get("require_consent", False))
