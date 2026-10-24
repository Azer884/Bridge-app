"""Customer-facing quotation text. The breakdown stays with the SME; the customer only ever
receives the approved estimate, and later the final price once the team has measured on site."""
from .i18n import STRINGS, t

INSPECTION_MESSAGE = STRINGS["en"]["inspection_message"]


def inspection_message(lang="en"):
    return t("inspection_message", lang)


def duration_text(schedule, lang="en"):
    """How long the job takes on site, from the calculation engine: "about 6 hours on site with a team of 2"."""
    if not schedule or not schedule.get("hours_on_site"):
        return ""
    hours, days, crew = schedule["hours_on_site"], schedule.get("working_days", 1), schedule.get("crew_size", 1)
    if lang == "ms":
        text = f"kira-kira {hours:g} jam di tapak dengan pasukan seramai {crew} orang"
        return text + (f", dalam {days} hari bekerja" if days > 1 else "")
    text = f"about {hours:g} hours on site with a team of {crew}"
    return text + (f", over {days} working days" if days > 1 else "")


def approved_quote_message(total, currency, business_name, lang="en", schedule=None):
    """The customer's dimensions may be wrong, so the approved number is an estimate until the site visit.
    It also says how long the job will take."""
    text = duration_text(schedule, lang)
    duration = t("duration", lang, text=text) if text else ""
    return t("approved", lang, business=business_name, currency=currency, total=total, duration=duration)


def final_quote_message(total, currency, business_name, lang="en"):
    return t("final", lang, business=business_name, currency=currency, total=total)
