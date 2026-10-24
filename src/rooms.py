"""More than one room in a job: "the master bedroom is 4 by 5 by 3 and the kids room is 3 by 3 by 3", "3 bedrooms each
4x4", "also the kitchen 3x3x2.5", "same size for the other bedroom".

The first room lives in the usual fields (room_length_m, room_width_m, room_height_m). Every further room is a dict in
verified["extra_rooms"] with the same keys plus a name. Surfaces, paint, colour, date and address are shared by all the
rooms. A room whose height is not given has the first room's height."""
import re

from .grounding import _SIZES, numbers_in, sizes_in, sizes_metric, unit_factors_in
from .schema import single_wall

_LABEL = re.compile(
    r"\b((?:(?:master|main|guest|kids?'?s?|children'?s?|baby|second|third|spare|small|big|living|dining|sitting|"
    r"first|another|other|new|my)\s+){0,2}(?:bed ?rooms?|rooms?|kitchen|bathroom|toilet|hall(?:way)?|study|office|"
    r"balcony|bilik(?: tidur| air| tamu| makan| anak)?|dapur|ruang tamu|tandas))\b", re.I)
_NAME_NOISE = {"my", "the", "a", "another", "other", "new", "first"}
_ADD = re.compile(r"\b(also|too|another|other|second|third|next|plus|and the|one more|as well|lagi|juga|tambah|add)\b", re.I)
_CORRECTION = re.compile(r"\b(sorry|meant|mistake|wrong|nvm|never ?mind|instead|change|actually|salah|silap|maksud)\b", re.I)
_SAME = re.compile(r"\b(same|sama)\b", re.I)
_ROOM_WORD = re.compile(r"\b(bed ?rooms?|rooms?|bilik|kitchen|bathroom|dapur|hall)\b", re.I)
_EACH = re.compile(
    r"\b(\d+|two|three|four|five|six|dua|tiga|empat|lima|enam)\s+((?:bed ?|bath)?rooms?|bilik(?: tidur)?)\b"
    r".{0,40}?\b(each|every|setiap|masing-masing|semua)\b", re.I)


def label_of(text):
    """The room named in `text` ("kids room"), the last one if several, lower case; "" when none."""
    found = list(_LABEL.finditer(text or ""))
    if not found:
        return ""
    words = [w for w in found[-1].group(1).lower().split() if w not in _NAME_NOISE]
    return " ".join(words)


def _metres(piece, state):
    """The numbers of one "4 by 5 by 3" piece in metres, or None when the unit is unclear."""
    numbers = sizes_in(piece)
    if not numbers or not all(n > 0 for n in numbers):
        return None
    said = unit_factors_in(piece)
    if len(said) > 1:
        return sizes_metric(piece)
    if len(said) == 1:
        factor = next(iter(said))
        return [round(n * factor, 3) for n in numbers]
    if state.unit_factor != 1.0:
        return [round(n * state.unit_factor, 3) for n in numbers]
    return numbers if all(1.5 <= n <= 8.0 for n in numbers) else None


def _room(name, sizes, one_wall):
    if len(sizes) >= 3:
        length, width, height = sizes[:3]
    elif one_wall:
        length, width, height = sizes[0], None, sizes[1]
    else:
        length, width, height = sizes[0], sizes[1], None
    return {"name": name, "room_length_m": length, "room_width_m": width, "room_height_m": height}


def sized_rooms(message, state):
    """Every "4 by 5 by 3" in the message as a room, named by the room word just before it. [] when a size is unclear."""
    one_wall = single_wall(state.verified.get("surfaces"))
    rooms, last_end = [], 0
    for match in _SIZES.finditer(message):
        sizes = _metres(match.group(0), state)
        if not sizes or len(sizes) < 2:
            return []
        rooms.append(_room(label_of(message[last_end:match.start()]), sizes, one_wall))
        last_end = match.end()
    return rooms


def copies(message):
    """"3 bedrooms each 4x4": how many rooms of that size (2 to 10), else 0."""
    found = _EACH.search(message)
    if not found:
        return 0
    count = numbers_in(found.group(1))
    return int(count[0]) if count and 2 <= count[0] <= 10 else 0


def wants_same_again(message):
    """"same for the other bedroom": one more room like the last one."""
    return bool(_SAME.search(message) and _ROOM_WORD.search(message) and _ADD.search(message))


def adds_room(message):
    return bool(_ADD.search(message))


def is_correction(message):
    return bool(_CORRECTION.search(message))


def strip_sizes(message):
    """The message without its "4 by 5 by 3" parts, so they are not read a second time as the first room's size."""
    return _SIZES.sub(" ", message)


def all_rooms(verified):
    """[(name, length, width, height)] for the whole job, the first room first. A room without a height has the first
    room's, and with a single wall there is no width."""
    first = (verified.get("room_name", ""), verified.get("room_length_m"), verified.get("room_width_m"),
             verified.get("room_height_m"))
    rooms = [first]
    for extra in verified.get("extra_rooms") or []:
        rooms.append((extra.get("name", ""), extra.get("room_length_m"), extra.get("room_width_m"),
                      extra.get("room_height_m") if extra.get("room_height_m") is not None else first[3]))
    return rooms


def fill_heights(verified):
    """A further room with no height of its own gets the first room's, once that is known."""
    height = verified.get("room_height_m")
    if height is None:
        return
    for extra in verified.get("extra_rooms") or []:
        if extra.get("room_height_m") is None:
            extra["room_height_m"] = height
