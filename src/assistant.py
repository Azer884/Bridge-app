"""One customer turn: build prompt, call model, validate, retry, fall back safely."""
from dataclasses import dataclass, field

import re

from . import contact, flow
from .persona import greeting_line, render
from .grounding import GroundingError, ground_field, ground_measurement, numbers_in
from .guard import MAX_STRIKES, REFUSAL, clip_message, screen_input
from .prompt import build_messages, load_system_prompt
from .runpod_client import RunPodError
from .schema import FIELDS, Status
from .validation import validate_response

MAX_RETRIES = 2
FALLBACK_REPLY = ("Thanks for your message. A member of our team will review your request "
                  "and get back to you shortly.")
INSPECTION_REPLY = ("Thanks for letting us know. That kind of work needs an inspection, so a "
                    "member of our team will contact you to arrange the next step.")


@dataclass
class TurnResult:
    reply: str
    status: str
    problems: list = field(default_factory=list)  # problems from the last failed attempt, if any
    attempts: int = 0


def handle_message(state, message, config, client, max_retries=MAX_RETRIES):
    message = clip_message(message)
    if screen_input(message):
        return _refuse(state, message, config)
    if state.stage == "done":
        return _finish(state, message, contact.DONE_REPLY, Status.READY.value)
    persona = config.get("persona")
    if state.stage == "contact":
        reply, finished = contact.handle_reply(state, message)
        if finished and persona:
            state.contact_confirmed, state.stage = True, "wrapup"
            return _finish(state, message, flow.wrapup_reply(state, config), Status.COLLECTING.value)
        status = Status.READY.value if finished else Status.COLLECTING.value
        return _finish(state, message, reply, status)
    if state.stage == "wrapup":
        if flow.is_yes(message):
            state.stage = "done"
            return _finish(state, message, flow.closing_reply(config), Status.READY.value)
        state.stage = "job"             # a correction: it goes through the normal flow below

    lowered = message.lower()
    if any(k in lowered for k in config.get("inspection_keywords", [])):
        return _finish(state, message, INSPECTION_REPLY, Status.HUMAN.value, human=True)

    if persona and not state.service_checked:
        service = flow.check_service(message)
        if service == "unsupported":
            return _finish(state, message, flow.decline_reply(config), Status.HUMAN.value, human=True)
        if service == "unknown":
            reply = _greet(state, config, render(persona["service_question"], persona, config))
            # kept out of the history so the first real turn still gets the format primer
            return _finish(state, message, reply, Status.COLLECTING.value, record=False)
        state.service_checked = True

    _resolve_pending_conflict(state, message)
    _prefill_measurement(state, message, config)
    system_prompt = load_system_prompt()
    rejection, problems, last = None, [], None
    for attempt in range(1, max_retries + 2):
        messages = build_messages(config, state, message, rejection, system_prompt)
        try:
            raw = client.chat(messages)
        except RunPodError as err:
            problems = [str(err)]
            break
        result = validate_response(raw, state, message, config)
        if result.ok:
            return _accept(state, message, config, result, attempt)
        problems = rejection = result.problems + result.soft_problems
        last = result

    if last is not None and set(last.problems) <= set(last.ungrounded):
        # Only values the customer never stated were wrong (they are already dropped, never stored)
        # or the reply's style was wrong (several questions). The model's reply may lean on the
        # dropped values, so the backend asks the next question itself instead of escalating.
        last.problems = []
        nxt = state.missing_required(config, extra=last.accepted)
        if nxt:
            last.reply = FIELDS[nxt[0]].ask
            last.soft_problems = []
            return _accept(state, message, config, last, max_retries + 1)
        if not last.soft_problems and not last.ungrounded:
            return _accept(state, message, config, last, max_retries + 1)

    # Failed turns stay out of the history so the model does not imitate them.
    out = _finish(state, message, FALLBACK_REPLY, Status.HUMAN.value, human=True, record=False)
    out.problems, out.attempts = problems, max_retries + 1
    return out


def _greet(state, config, reply):
    """The persona says hello once, in front of the first reply."""
    persona = config.get("persona")
    if not persona or state.greeted:
        return reply
    state.greeted = True
    return f"{greeting_line(persona, config)} {reply}"


def _accept(state, message, config, result, attempt):
    state.merge(result.accepted)
    result.reply = _greet(state, config, result.reply)
    if result.conflicts:
        key, old, new = result.conflicts[0]
        state.pending_conflict = {"key": key, "old": old, "new": new}
        reply = (f"Earlier you told me the {FIELDS[key].label.lower()} was {_show(key, old)}, but "
                 f"now it sounds like {_show(key, new)}. Which one is correct?")
        out = _finish(state, message, reply, Status.CLARIFICATION.value, extracted=result.accepted)
    elif result.status != Status.HUMAN.value and not state.missing_required(config):
        # Job details complete: the backend (not the model) now confirms the booking contact.
        if config.get("persona") and state.contact_confirmed:
            state.stage = "wrapup"      # contact already confirmed: recap again after a correction
            reply = flow.wrapup_reply(state, config)
        elif config.get("persona"):
            reply = flow.contact_intro(state)
        else:
            reply = contact.begin(state)
        out = _finish(state, message, reply, Status.COLLECTING.value, extracted=result.accepted)
    else:
        human = result.status == Status.HUMAN.value
        out = _finish(state, message, result.reply, result.status, human=human,
                      extracted=result.accepted)
    out.attempts = attempt
    return out


def _refuse(state, message, config):
    """Blocked message: never sent to the model, never stored in the history."""
    state.strikes += 1
    if state.strikes >= MAX_STRIKES:
        return _finish(state, message, FALLBACK_REPLY, Status.HUMAN.value, human=True, record=False)
    if state.stage == "contact":
        question = contact._prompt(state)
    else:
        nxt = state.next_missing(config)
        question = FIELDS[nxt].ask if nxt else ""
    return _finish(state, message, f"{REFUSAL} {question}".strip(),
                   Status.COLLECTING.value, record=False)


_CUES = {"room_length_m": {"long", "length"}, "room_width_m": {"wide", "width"},
         "room_height_m": {"high", "tall", "height"}}


def _prefill_measurement(state, message, config):
    """Short answers like '3 metres wide' are parsed here, not left to the model.

    Only fills a missing measurement; one number and one unit are required, and a cue word
    (long/wide/high) beats question order. Anything ambiguous is left to the normal flow.
    """
    missing = state.missing_required(config)
    open_fields = [k for k in missing if k in _CUES]
    numbers = numbers_in(message)
    if not open_fields or len(numbers) != 1:
        return
    words = set(re.findall(r"[a-z]+", message.lower()))
    if any(_CUES[k] & words for k in _CUES if k not in open_fields):
        return  # the cue is for a field we already have: let the conflict flow handle it
    cued = [k for k in open_fields if _CUES[k] & words]
    if len(cued) == 1:
        key = cued[0]
    elif not cued and missing[0] in _CUES:
        key = missing[0]
    else:
        return
    try:
        state.verified[key] = ground_measurement(numbers[0], message)
    except GroundingError:
        return


def _show(key, value):
    return f"{value:g} metres" if FIELDS[key].kind == "measurement" else str(value)


def _resolve_pending_conflict(state, message):
    """The customer's explicit answer to a clarifying question settles the conflicting field."""
    pending = state.pending_conflict
    if not pending:
        return
    try:
        value = ground_field(FIELDS[pending["key"]], message, message)
    except GroundingError:
        return  # no usable answer yet; keep asking
    state.verified[pending["key"]] = value
    state.pending_conflict = None


def _finish(state, message, reply, status, human=False, extracted=None, record=True):
    if record:
        state.add_turn(message, reply, status, extracted)
    state.status = status
    state.needs_human = state.needs_human or human
    return TurnResult(reply=reply, status=status)
