"""Customer-facing quotation text. The breakdown stays with the SME; the customer only ever
receives the approved estimate, and later the final price once the team has measured on site."""
from .i18n import STRINGS, t
from .rooms import all_rooms
from .schema import single_wall

_SURFACE_MS = {"one wall": "satu dinding", "walls": "dinding", "wall": "dinding", "ceiling": "siling"}

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


def _size(length, width, height, one_wall):
    if one_wall or width is None:
        return f"{length or 0:g} m x {height or 0:g} m"
    return f"{length or 0:g} x {width:g} x {height or 0:g} m"


def job_lines(verified, lang="en"):
    """The job as short lines: each room's size, the surfaces, paint, colour and preferred date."""
    verified = verified or {}
    lines, one_wall = [], single_wall(verified.get("surfaces"))
    rooms = [r for r in all_rooms(verified) if r[1] is not None]
    for number, (name, length, width, height) in enumerate(rooms, start=1):
        label = (name or t("est_room_name", lang, n=number)) if len(rooms) > 1 or name else t("est_room_name", lang, n=1)
        label = label[:1].upper() + label[1:]
        if len(rooms) == 1 and not name:
            label = "Bilik" if lang == "ms" else "Room"
        lines.append(t("est_room", lang, name=label, size=_size(length, width, height, one_wall)))
    surfaces = verified.get("surfaces")
    if surfaces:
        shown = [(_SURFACE_MS.get(str(s).lower(), s) if lang == "ms" else s) for s in surfaces]
        lines.append(t("est_surfaces", lang, value=", ".join(shown)))
    if verified.get("paint_tier"):
        lines.append(t("est_paint", lang, value=verified["paint_tier"]))
    if verified.get("colour"):
        lines.append(t("est_colour", lang, value=verified["colour"]))
    return lines


def approved_quote_message(total, currency, business_name, lang="en", schedule=None, verified=None, pdf=False):
    """The approved estimate as a short list: the price first, then the job, the time it takes and the date. The
    customer's dimensions may be wrong, so it is an estimate until the site visit."""
    bullets = [t("est_total", lang, currency=currency, total=total)] + job_lines(verified, lang)
    text = duration_text(schedule, lang)
    if text:
        bullets.append(t("est_time", lang, value=text))
    if (verified or {}).get("preferred_datetime"):
        bullets.append(t("est_date", lang, value=verified["preferred_datetime"]))
    parts = [t("est_head", lang, business=business_name), "\n".join("• " + b for b in bullets), t("est_note", lang)]
    if pdf:
        parts.append(t("est_pdf", lang))
    return "\n\n".join(parts)


def final_quote_message(total, currency, business_name, lang="en", verified=None):
    bullets = [t("final_total", lang, currency=currency, total=total)] + job_lines(verified, lang)
    return "\n\n".join([t("final_head", lang, business=business_name), "\n".join("• " + b for b in bullets),
                        t("final_note", lang)])
