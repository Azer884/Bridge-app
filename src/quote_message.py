"""Customer-facing quotation text. The breakdown stays with the SME; the customer only ever
receives the approved estimate, and later the final price once the team has measured on site."""
from .i18n import STRINGS, t

INSPECTION_MESSAGE = STRINGS["en"]["inspection_message"]


def inspection_message(lang="en"):
    return t("inspection_message", lang)


def approved_quote_message(total, currency, business_name, lang="en"):
    """The customer's dimensions may be wrong, so the approved number is an estimate until the site visit."""
    return t("approved", lang, business=business_name, currency=currency, total=total)


def final_quote_message(total, currency, business_name, lang="en"):
    return t("final", lang, business=business_name, currency=currency, total=total)
