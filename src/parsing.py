"""Pull one JSON object out of raw model text (fences, surrounding prose)."""
import json


class ParseError(ValueError):
    pass


def extract_json(text):
    if not isinstance(text, str) or not text.strip():
        raise ParseError("empty model output")
    start = text.find("{")
    while start != -1:
        end = _matching_brace(text, start)
        if end != -1:
            try:
                obj = json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                obj = None
            if isinstance(obj, dict):
                return obj
        start = text.find("{", start + 1)
    raise ParseError("no valid JSON object found in model output")


def _matching_brace(text, start):
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1
