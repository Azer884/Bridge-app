"""A one-page text PDF for the customer's estimate, written by hand (no PDF library to install).

The estimate letter shows the job and the estimated total only: the price breakdown stays with the owner.
"""
from datetime import datetime

from .calendar_scheduler import TZ
from .quote_message import duration_text


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
    stream = "\n".join(body).encode("latin-1")
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
    surfaces = job.get("surfaces") or "-"
    size = (f"{job['room_length_m']:g} m long x {job['room_height_m']:g} m high" if job.get("room_width_m") is None
             else f"{job['room_length_m']:g} x {job['room_width_m']:g} x {job['room_height_m']:g} m")
    more = job.get("extra_rooms") or []
    if more:
        size += "".join(
            f"; {e.get('name') or 'room'} {e['room_length_m']:g} x {e.get('room_width_m') or 0:g} x {e.get('room_height_m') or 0:g} m"
            for e in more)
    lines = [(business, 20, True), ("Painting estimate", 14, True),
             (datetime.now(TZ).strftime("%d %b %Y"), 10, False), ("", 8, False),
             (f"Customer: {customer}", 11, False), (f"Address: {job.get('address') or '-'}", 11, False),
             (f"Surfaces: {surfaces}", 11, False), (f"Size: {size}", 11, False),
             (f"Paint: {job.get('paint_tier') or 'standard'}", 11, False), ("", 8, False),
             (f"Estimated total: {quote['currency']} {total:,.2f} (excluding any applicable tax)", 14, True)]
    time_needed = duration_text(quote.get("schedule"))
    if time_needed:
        lines.append((f"Estimated time: {time_needed}", 11, False))
    lines += [("", 8, False),
              ("This is an estimate based on the dimensions you gave us. The final price is confirmed after our team "
               "has measured on site.", 10, False)]
    return make_pdf(lines)
