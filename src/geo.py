"""Is a shared WhatsApp location inside Malaysia? Gesir only quotes jobs there.

The outlines are coarse (about 10 to 20 km of margin) and built into the code, so no outside service sees a customer's
location. A pin on a coast can fall either side; a pin in the sea, in another country or on another continent never passes.
"""
import re

# (longitude, latitude) outlines, clockwise
PENINSULA = [(100.12, 6.50), (100.65, 6.50), (101.10, 6.30), (102.10, 6.30), (102.40, 6.00), (102.95, 5.65), (103.25, 5.20),
             (103.50, 4.60), (103.55, 3.60), (103.50, 2.95), (103.95, 2.40), (104.40, 1.75), (104.35, 1.40), (103.85, 1.25),
             (103.45, 1.25), (103.00, 1.50), (102.60, 1.85), (102.20, 2.15), (101.80, 2.50), (101.35, 2.95), (101.05, 3.65),
             (100.70, 4.20), (100.45, 4.90), (100.25, 5.40), (100.30, 5.95)]
BORNEO = [(109.40, 2.15), (110.20, 2.05), (111.00, 2.45), (112.00, 3.05), (113.10, 3.50), (114.00, 4.65), (114.90, 5.20),
          (115.40, 5.60), (116.00, 6.25), (116.60, 7.15), (117.05, 7.20), (117.60, 6.90), (118.40, 6.25), (119.15, 5.60),
          (119.35, 4.80), (118.60, 4.10), (117.40, 4.05), (116.40, 4.10), (115.85, 3.80), (115.35, 2.95), (114.65, 2.00),
          (113.50, 1.15), (112.30, 1.30), (111.30, 0.90), (110.40, 1.10), (109.90, 1.45)]
LANGKAWI = [(99.60, 6.20), (99.95, 6.20), (99.95, 6.55), (99.60, 6.55)]
SINGAPORE = [(103.55, 1.15), (104.15, 1.15), (104.15, 1.47), (103.55, 1.47)]


def _inside(lon, lat, polygon):
    """Ray casting: is the point inside the polygon?"""
    inside, j = False, len(polygon) - 1
    for i, (xi, yi) in enumerate(polygon):
        xj, yj = polygon[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def in_malaysia(lat, lon):
    """True for a latitude and longitude inside Malaysia (the peninsula, Sabah, Sarawak, Labuan, Langkawi)."""
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return False
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return False
    if _inside(lon, lat, SINGAPORE):
        return False
    return any(_inside(lon, lat, shape) for shape in (PENINSULA, BORNEO, LANGKAWI))


_FOREIGN = re.compile(
    r"\b(indonesia|jakarta|bandung|surabaya|medan|batam|bali|yogyakarta|singapore|singapura|thailand|bangkok|brunei|"
    r"philippines|manila|vietnam|hanoi|cambodia|myanmar|india|china|hong kong|japan|korea|australia|"
    r"united kingdom|london|usa|united states|new york|dubai)\b", re.I)


def foreign_place(text):
    """True when typed text puts the job in another country ("Jakarta", "Singapore"). A pin is checked by
    in_malaysia; this covers an address typed in words."""
    return bool(_FOREIGN.search(text or ""))
