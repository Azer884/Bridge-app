"""A one-page text PDF for the customer's estimate, written by hand (no PDF library to install).

The estimate letter shows the job and the estimated total only: the price breakdown stays with the owner.
"""
from datetime import datetime

from .calendar_scheduler import TZ
from .quote_message import duration_text, job_lines


def _escape(text):
    clean = text.encode("latin-1", "replace").decode("latin-1")
    return clean.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(lines):
    """lines: (text, size, bold). Returns the bytes of a valid single-page A4 PDF."""
    body, y = [], 790
    for text, size, bold in lines:
        y -= size + 6
        for chunk in [text[i:i + 90] for i in range(0, max(len(text), 1), 90)]:
            body.append(f"BT /F{2 if bold else 1} {size} Tf 56 {y} Td ({_escape(chunk)}) Tj ET")
            y -= 0 if len(text) <= 90 else size + 2
    stream = "\n".join(body).encode("latin-1", "replace")      # the built-in PDF fonts only have Latin-1
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    ]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for number, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def estimate_pdf(business, customer, job, quote):
    """The estimate letter for one customer. `quote` is the engine's dict (its total and schedule are used)."""
    total = quote.get("approved_total") or quote["total"]
    verified = {"surfaces": [s.strip() for s in (job.get("surfaces") or "").split(",") if s.strip()],
                "room_length_m": job.get("room_length_m"), "room_width_m": job.get("room_width_m"),
                "room_height_m": job.get("room_height_m"), "room_name": job.get("room_name") or "",
                "extra_rooms": job.get("extra_rooms") or [], "paint_tier": job.get("paint_tier") or "standard",
                "colour": job.get("colour")}
    lines = [(business, 20, True), ("Painting estimate", 14, True),
             (datetime.now(TZ).strftime("%d %b %Y"), 10, False), ("", 8, False),
             (f"Customer: {customer}", 11, False), (f"Address: {job.get('address') or '-'}", 11, False), ("", 6, False)]
    lines += [("- " + line, 11, False) for line in job_lines(verified)]
    if job.get("preferred_datetime"):
        lines.append((f"- Preferred date: {job['preferred_datetime']}", 11, False))
    lines += [("", 8, False),
              (f"Estimated total: {quote['currency']} {total:,.2f} (excluding any applicable tax)", 14, True)]
    time_needed = duration_text(quote.get("schedule"))
    if time_needed:
        lines.append((f"Estimated time: {time_needed}", 11, False))
    lines += [("", 8, False),
              ("This is an estimate based on the dimensions you gave us. The final price is confirmed after our team "
               "has measured on site.", 10, False)]
    return make_pdf(lines)
