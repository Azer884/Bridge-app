"""One customer turn: build prompt, call model, validate, retry, fall back safely."""
from dataclasses import dataclass, field

import re
import time
from types import SimpleNamespace

from . import contact, flow
from .grounding import (GroundingError, estimate_in, ground_field, ground_measurement, numbers_in,
                        sizes_in, unit_factors_in)
from .guard import MAX_STRIKES, clip_message, screen_input
from .i18n import STRINGS, TIER_WORDS, detect, metres, requested_language, t
from .persona import greeting_line, render, text as persona_text
from .prompt import build_messages, load_system_prompt
from .runpod_client import RunPodError
from .schema import FIELDS, Status, ask_for
from .validation import validate_response

MAX_RETRIES = 2
FALLBACK_REPLY = STRINGS["en"]["fallback"]
INSPECTION_REPLY = STRINGS["en"]["inspection_reply"]


@dataclass
class TurnResult:
    reply: str
    status: str
    problems: list = field(default_factory=list)  # problems from the last failed attempt, if any
    attempts: int = 0


def _current_question(state, config):
    """What the customer is being asked right now, to repeat after a side answer or a language switch."""
    if state.stage == "contact":
        return contact._prompt(state)
    if state.stage == "wrapup":
        return t("wrap_ok", state.lang)
    if state.stage == "done":
        return ""
    nxt = state.next_missing(config)
    return ask_for(nxt, state) if nxt else ""


def handle_message(state, message, config, client, max_retries=MAX_RETRIES):
    message = clip_message(message)
    asked = requested_language(message)
    state.lang = asked or detect(message, state.lang)
    if asked:                           # "speak Malay" / "in English please": switch and carry on
        rest = " ".join(part.strip() for part in re.split(r"[\n.!?]+", message)
                        if part.strip() and not requested_language(part))
        if rest and not screen_input(rest):     # "Back to English pls" + "Any time": answer the rest too
            out = handle_message(state, rest, config, client, max_retries)
            state.lang = asked
            out.reply = f"{t('lang_' + asked, asked)} {out.reply}".strip()
            return out
        return _finish(state, message, f"{t('lang_' + asked, asked)} {_current_question(state, config)}".strip(),
                       Status.COLLECTING.value, record=False)
    if flow.wants_restart(message):
        flow.restart_job(state) if state.stage != "done" else flow.start_new_order(state)
        first = ask_for(state.next_missing(config), state) if state.next_missing(config) else ""
        return _finish(state, message, f"{t('restart', state.lang)} {first}".strip(),
                       Status.COLLECTING.value, record=False)
    if screen_input(message):
        return _refuse(state, message, config)
    persona = config.get("persona")
    if state.stage == "done":
        if flow.new_job_intent(message, state):
            flow.start_new_order(state)         # a returning customer: archive the old job, start a new one
        else:
            return _after_done(state, message, config)
    if flow.is_correction(message) and state.stage in ("contact", "wrapup", "job"):
        fixed = _correct_measurement(state, message)
        if fixed:
            return _after_correction(state, message, config, fixed)
    if state.stage == "contact":
        faq = flow.faq_answer(message, config, "contact", state.lang) if persona else None
        if faq and not contact.find_phone(message):
            return _finish(state, message, f"{faq} {contact._prompt(state)}", Status.COLLECTING.value,
                           record=False)
        reply, finished = contact.handle_reply(state, message)
        if finished and persona:
            state.contact_confirmed, state.stage = True, "wrapup"
            return _finish(state, message, flow.wrapup_reply(state, config), Status.COLLECTING.value)
        status = Status.READY.value if finished else Status.COLLECTING.value
        return _finish(state, message, reply, status)
    if state.stage == "wrapup":
        if flow.is_yes(message):
            state.stage = "done"
            return _finish(state, message, flow.closing_reply(state, config), Status.READY.value)
        faq = flow.faq_answer(message, config, "wrapup", state.lang)
        if faq:                         # a side question: answer it, then ask for the confirmation again
            return _finish(state, message, f"{faq} {t('wrap_ok', state.lang)}", Status.COLLECTING.value,
                           record=False)
        state.stage = "job"             # a correction: it goes through the normal flow below

    lowered = message.lower()
    if any(k in lowered for k in config.get("inspection_keywords", [])):
        return _finish(state, message, t("inspection_reply", state.lang), Status.HUMAN.value, human=True)

    if persona and not state.service_checked:
        service = flow.check_service(message)
        if service == "unsupported":
            return _finish(state, message, flow.decline_reply(state, config), Status.HUMAN.value, human=True)
        if service == "unknown":
            reply = _greet(state, config, render(persona_text(persona, "service_question", state.lang),
                                                  persona, config))
            # kept out of the history so the first real turn still gets the format primer
            return _finish(state, message, reply, Status.COLLECTING.value, record=False)
        state.service_checked = True

    if persona:
        faq = flow.faq_answer(message, config, "job", state.lang)
        nxt = state.next_missing(config)
        if faq and nxt:                 # a side question in the middle of the job: answer, then carry on
            return _finish(state, message, f"{faq} {ask_for(nxt, state)}", Status.COLLECTING.value, record=False)

    _resolve_pending_conflict(state, message)
    asked = state.next_missing(config)              # the question the customer is answering
    before, before_estimated = dict(state.verified), list(state.estimated)
    _prefill_job(state, message, config)
    if "surfaces" not in changed_keys(before, state):         # a number next to "one wall" is a count
        _prefill_measurement(state, message, config)
    changed = {k for k, v in state.verified.items() if before.get(k) != v}   # read by the backend this turn
    system_prompt = load_system_prompt()
    if persona and changed:
        return _backend_turn(state, message, config, client, changed, system_prompt,
                             estimated=len(state.estimated) > len(before_estimated), asked=asked)
    rejection, problems, last = None, [], None
    for attempt in range(1, max_retries + 2):
        messages = build_messages(config, state, message, rejection, system_prompt)
        try:
            raw = client.chat(messages)
        except RunPodError as err:
            problems = [str(err)]
            break
        result = validate_response(raw, state, message, config)
        result.conflicts = [c for c in result.conflicts if c[0] not in changed]   # the backend's reading wins
        for key in changed:
            result.accepted.pop(key, None)
        if not changed:
            _keep_plain_answer(state, message, asked, result.accepted)
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
            last.reply = ask_for(nxt[0], state)
            last.soft_problems = []
            return _accept(state, message, config, last, max_retries + 1)
        if not last.soft_problems and not last.ungrounded:
            return _accept(state, message, config, last, max_retries + 1)

    # Failed turns stay out of the history so the model does not imitate them.
    out = _finish(state, message, t("fallback", state.lang), Status.HUMAN.value, human=True, record=False)
    out.problems, out.attempts = problems, max_retries + 1
    return out


_FREE_TEXT = {"surface_condition": 160, "colour": 60, "address": 160}
_FILLER = contact.AFFIRMATIVE | contact.NEGATIVE | {"hi", "hello", "hai", "helo", "hey", "thanks", "thank",
                                                     "terima", "kasih", "bye", "lol", "haha", "hmm"}


def _keep_plain_answer(state, message, asked, accepted):
    """The model did not record the answer to the question it asked (often because it rephrased or
    translated the customer's words, and the check against the message then drops it). A short plain
    reply to a free-text question is kept in the customer's own words: those are grounded by definition."""
    limit = _FREE_TEXT.get(asked)
    if not limit or asked in accepted or asked in state.verified:
        return
    text = message.strip()
    words = re.findall(r"[a-z']+", text.lower())
    if not text or "?" in text or len(text) > limit or all(w in _FILLER for w in words) or flow.is_correction(text):
        return
    if asked == "address" and not (re.search(r"\d", text) or len(words) >= 2):
        return
    accepted[asked] = text


def _after_done(state, message, config):
    """The chat is complete and the SME has not (or has) confirmed: answer what matters, stay quiet otherwise."""
    fixed = _correct_measurement(state, message) if flow.is_correction(message) else None
    if fixed:
        if state.quote_status in ("pending_approval", "needs_inspection"):
            state.quote_stale = True            # the draft is recalculated from the corrected size
        state.attention = True
        return _finish(state, message, fixed, Status.READY.value, record=False)
    reply = flow.after_done(state, message, config)
    if reply is None:                           # silence: the SME will confirm, nothing useful to add
        return _finish(state, message, "", Status.READY.value, record=False)
    return _finish(state, message, reply, Status.READY.value)


_ACKS = ["ack_1", "ack_2", "ack_3", "ack_4", "ack_5"]


def _backend_turn(state, message, config, client, changed, system_prompt, estimated=False, asked=None):
    """The backend already read this answer (surface, measurement, date...). The model is still asked once
    for anything else the message says, but its reply is not used: it tends to ask for the value the
    backend just filled in. The backend acknowledges and asks the next question itself."""
    accepted = {}
    if state.missing_required(config):          # nothing left to ask: no model call is needed
        try:
            raw = client.chat(build_messages(config, state, message, None, system_prompt))
            result = validate_response(raw, state, message, config)
            accepted = {k: v for k, v in result.accepted.items() if k not in changed}
        except RunPodError:
            pass
    state.merge(accepted)
    ack = (t("ack_estimate", state.lang) if estimated
           else t(_ACKS[(len(state.history) // 2) % len(_ACKS)], state.lang))
    missing = state.missing_required(config)
    reply = f"{ack} {ask_for(missing[0], state)}" if missing else ""
    done = SimpleNamespace(accepted=accepted, conflicts=[], reply=reply,
                           status=Status.COLLECTING.value if missing else Status.READY.value)
    return _accept(state, message, config, done, 1)


def _greet(state, config, reply):
    """The persona says hello once, in front of the first reply."""
    persona = config.get("persona")
    if not persona or state.greeted:
        return reply
    state.greeted = True
    return f"{greeting_line(persona, config, state.lang)} {reply}"


def _accept(state, message, config, result, attempt):
    state.merge(result.accepted)
    for key in result.accepted:
        if FIELDS[key].kind == "measurement":
            state.last_field = key
    if result.conflicts and flow.is_correction(message):
        for key, _old, new in result.conflicts:     # an explicit "nvm, it's ..." is the answer: no question
            state.verified[key] = new
            if FIELDS[key].kind == "measurement":
                state.last_field = key
        result.conflicts = []
    result.reply = _greet(state, config, result.reply)
    if result.conflicts:
        key, old, new = result.conflicts[0]
        state.pending_conflict = {"key": key, "old": old, "new": new}
        reply = t("conflict", state.lang, label=t(f"label_{key}", state.lang), old=_show(key, old, state.lang),
                  new=_show(key, new, state.lang))
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
        return _finish(state, message, t("fallback", state.lang), Status.HUMAN.value, human=True, record=False)
    question = _current_question(state, config)
    return _finish(state, message, f"{t('refusal', state.lang)} {question}".strip(),
                   Status.COLLECTING.value, record=False)


# --- answers the backend reads itself -------------------------------------------------------------
_WALLS = re.compile(r"\b(walls|semua dinding|dinding-dinding|keempat-empat dinding)\b", re.I)
_WALL = re.compile(r"\b(wall|(satu|1|sebelah|sebuah) dinding|dinding (satu|ini|itu|sahaja|saja))\b", re.I)
_PLAIN_DINDING = re.compile(r"\bdinding\b", re.I)
_CEILING = re.compile(r"\b(ceilings?|siling)\b", re.I)
_TIERS = re.compile(r"\b(economy|ekonomi|standard|premium)\b", re.I)
PHOTO_CONDITION = "see the customer's photo"


def changed_keys(before, state):
    return {k for k, v in state.verified.items() if before.get(k) != v}


def _prefill_job(state, message, config):
    """Answers the backend can read without the model: which surfaces, when, the condition shown in a
    photo, and "no preference". Only the field being asked about (or a clearly stated surface) is filled,
    so a short reply is never lost and the customer is never asked the same thing twice."""
    missing = state.missing_required(config)
    if "surfaces" in missing:
        items = []
        if _WALLS.search(message):
            items.append("walls")
        elif _WALL.search(message):
            items.append("one wall")        # a singular "wall" means one wall: length x height is enough
        elif _PLAIN_DINDING.search(message):
            items.append("walls")           # Malay "dinding" with no number: the walls of the room
        if _CEILING.search(message):
            items.append("ceiling")
        if items:
            state.verified["surfaces"] = items
            missing = state.missing_required(config)
    if "surface_condition" in missing and state.photo_assessment:
        state.verified["surface_condition"] = PHOTO_CONDITION      # the photo already shows it
        missing = state.missing_required(config)
    if not missing:
        return
    key = missing[0]
    if key == "preferred_datetime":
        when = flow.when_in(message)
        if when:
            state.verified[key] = when
    elif key == "surface_condition" and flow._BARE_NO.match(message):
        state.verified[key] = "no visible damage reported"
    elif key == "paint_tier":
        tier = _TIERS.search(message)
        if tier:
            state.verified[key] = TIER_WORDS[tier.group(1).lower()]
        elif flow.NO_PREFERENCE.search(message):
            state.verified[key] = "no preference"
    elif key == "colour" and flow.NO_PREFERENCE.search(message):
        state.verified[key] = "no preference"
    elif key == "address" and state.orders and flow.is_yes(message):
        previous = state.orders[-1]["verified"].get("address")      # a returning customer, same address
        if previous:
            state.verified[key] = previous


# A plain number answering a size question is metres when it is a believable room size; 10 or 12 could
# be feet, and a number next to "wall", "room", "coat"... is a count, so those are left to the model.
PLAIN_METRES = (1.5, 8.0)
_COUNT_NOUNS = re.compile(r"\b(walls?|ceilings?|rooms?|bedrooms?|doors?|windows?|coats?|floors?|dinding|siling|"
                          r"bilik|pintu|tingkap)\b", re.I)
_CUES = {"room_length_m": {"long", "length", "panjang"}, "room_width_m": {"wide", "width", "lebar"},
         "room_height_m": {"high", "tall", "height", "tinggi"}}


def _prefill_measurement(state, message, config):
    """Short answers like '3 metres wide' are parsed here, not left to the model.

    Only fills a missing measurement; one number and one unit are required, and a cue word
    (long/wide/high) beats question order. Anything ambiguous is left to the normal flow.
    """
    missing = state.missing_required(config)
    open_fields = [k for k in missing if k in _CUES]
    sizes = sizes_in(message)
    if sizes and len(open_fields) >= len(sizes):
        # "4 by 5": the next open measurements in order (length then width, or length then height for one wall)
        if not unit_factors_in(message) and not all(PLAIN_METRES[0] <= n <= PLAIN_METRES[1] for n in sizes):
            return                      # "10 by 12" could be feet: the model asks which
        text = message if unit_factors_in(message) else f"{message} m"
        try:
            values = [ground_measurement(n, text) for n in sizes]
        except GroundingError:
            return
        _, hedged = estimate_in(message)
        for key, value in zip(open_fields, values):
            state.verified[key] = value
            state.last_field = key
            if hedged and key not in state.estimated:
                state.estimated.append(key)
        return
    numbers = numbers_in(message)
    upper, estimated = estimate_in(message)
    if upper is not None:
        numbers = [upper]               # "4 to 5 m": use the larger figure, flag it as an estimate
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
    text = message if unit_factors_in(message) or upper is None else f"{message} m"
    try:
        # the customer is answering this very question, so a plain number is metres ("I said 5")
        assume = (key == missing[0] and PLAIN_METRES[0] <= numbers[0] <= PLAIN_METRES[1]
                  and not _COUNT_NOUNS.search(message))
        state.verified[key] = ground_measurement(numbers[0], text, assume_metres=assume)
    except GroundingError:
        return
    state.last_field = key
    if estimated and key not in state.estimated:
        state.estimated.append(key)


def _correct_measurement(state, message):
    """"nvm its 4m": replace the measurement the customer gave last (or the one they name). Returns the
    acknowledgement, or None when the message is not a clear correction of a size."""
    upper, estimated = estimate_in(message)
    numbers = [upper] if upper is not None else numbers_in(message)
    if len(numbers) != 1:
        return None
    words = set(re.findall(r"[a-z]+", message.lower()))
    cued = [k for k in _CUES if _CUES[k] & words]
    if len(cued) > 1:
        return None
    key = cued[0] if cued else state.last_field
    if key not in _CUES or key not in state.verified:
        return None
    text = message if unit_factors_in(message) or upper is None else f"{message} m"
    try:
        value = ground_measurement(numbers[0], text)
    except GroundingError:
        return None
    state.verified[key], state.last_field = value, key
    if estimated and key not in state.estimated:
        state.estimated.append(key)
    elif not estimated and key in state.estimated:
        state.estimated.remove(key)
    return t("ack_fixed", state.lang, label=t(f"label_{key}", state.lang), value=metres(value, state.lang))


def _after_correction(state, message, config, fixed):
    """A size was corrected: confirm it, then continue from where the chat is."""
    if state.stage == "contact":
        return _finish(state, message, f"{fixed} {contact._prompt(state)}", Status.COLLECTING.value, record=False)
    if state.stage == "wrapup":
        return _finish(state, message, f"{fixed}\n\n{flow.recap(state)}\n\n{t('wrap_ok', state.lang)}",
                       Status.COLLECTING.value, record=False)
    missing = state.missing_required(config)
    done = SimpleNamespace(accepted={}, conflicts=[], status=Status.COLLECTING.value if missing else Status.READY.value,
                           reply=f"{fixed} {ask_for(missing[0], state)}" if missing else fixed)
    return _accept(state, message, config, done, 1)


def _show(key, value, lang="en"):
    return metres(value, lang) if FIELDS[key].kind == "measurement" else str(value)


def _resolve_pending_conflict(state, message):
    """The customer's explicit answer to a clarifying question settles the conflicting field."""
    pending = state.pending_conflict
    if not pending:
        return
    spec = FIELDS[pending["key"]]
    if spec.kind == "measurement":
        candidates = [message]
    else:
        # a text answer must point at one of the two values, not be any unrelated message
        candidates = [pending["new"], pending["old"]]
    value = None
    for candidate in candidates:
        try:
            value = ground_field(spec, candidate, message)
            break
        except GroundingError:
            continue
    if value is None:
        return  # no usable answer yet; keep asking
    state.verified[pending["key"]] = value
    state.pending_conflict = None


def _finish(state, message, reply, status, human=False, extracted=None, record=True):
    if record:
        state.add_turn(message, reply, status, extracted)
    state.status = status
    state.needs_human = state.needs_human or human
    return TurnResult(reply=reply, status=status)
