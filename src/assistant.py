"""One customer turn: build prompt, call model, validate, retry, fall back safely."""
from dataclasses import dataclass, field

import re
import time
from types import SimpleNamespace

from . import contact, flow, geo
from .grounding import (HEDGES, ONES, UNIT_FACTORS, GroundingError, cued_sizes, estimate_in, ground_field,
                        _bare_number, ground_measurement, numbers_in, sizes_in, sizes_metric, spoken_decimals,
                        unit_factors_in)
from .guard import MAX_STRIKES, clip_message, is_abusive, screen_input
from . import rooms as rooms_module
from .answers import CONDITION_STRONG, address_in, condition_clause, explicit_name, fix_typos, is_condition, plausible
from .i18n import COLOUR_WORDS, STRINGS, TIER_WORDS, detect, metres, requested_language, t, us_spelling
from .persona import greeting_line, render, text as persona_text
from .prompt import build_messages, load_system_prompt, trade_of
from .runpod_client import RunPodError
from .schema import FIELDS, Status, ask_for, single_wall
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


def _current_question(state, config, service=False):
    """What the customer is being asked right now, to repeat after a side answer or a language switch."""
    if state.stage == "contact":
        return contact._prompt(state)
    if state.stage == "wrapup":
        return t("wrap_ok", state.lang)
    if state.stage == "done":
        return ""
    persona = config.get("persona")
    if service and persona and not state.service_checked:
        return render(persona_text(persona, "service_question", state.lang), persona, config, state.lang)
    nxt = state.next_missing(config)
    return ask_for(nxt, state) if nxt else ""


def handle_message(state, message, config, client, max_retries=MAX_RETRIES):
    """One customer message in, one reply out. The persona says hello in front of the first reply, and a side
    answer given while the details in the message were still read goes in front of the question that follows."""
    state._faq_prefix = ""
    out = _handle(state, message, config, client, max_retries)
    prefix, state._faq_prefix = state._faq_prefix, ""
    persona = config.get("persona")
    if prefix and out.reply:
        hello = greeting_line(persona, config, state.lang) if persona else ""
        if hello and out.reply.startswith(hello):
            out.reply = f"{hello} {prefix} {out.reply[len(hello):].strip()}"
        else:
            out.reply = f"{prefix} {out.reply}"
    if persona and out.reply and not state.greeted:
        out.reply = _greet(state, config, out.reply)
    return out


def _handle(state, message, config, client, max_retries=MAX_RETRIES):
    message = spoken_decimals(fix_typos(clip_message(message)))
    message = re.sub(r"(?<=\d)'", " ft ", message)              # 12'x10' is feet
    if state.stage == "job":
        _volunteer(state, message)                              # a name, number or address mentioned in passing
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
        return _finish(state, message, f"{t('lang_' + asked, asked)} {_current_question(state, config, service=True)}".strip(),
                       Status.COLLECTING.value, record=False)
    if flow.wants_restart(message):
        flow.restart_job(state) if state.stage != "done" else flow.start_new_order(state)
        first = ask_for(state.next_missing(config), state) if state.next_missing(config) else ""
        return _finish(state, message, f"{t('restart', state.lang)} {first}".strip(),
                       Status.COLLECTING.value, record=False)
    if screen_input(message):
        return _refuse(state, message, config)
    persona = config.get("persona")
    if is_abusive(message):
        state.strikes += 1                      # polite once or twice, then a person takes over
        if state.strikes >= MAX_STRIKES:
            return _finish(state, message, t("fallback", state.lang), Status.HUMAN.value, human=True, record=False)
        return _finish(state, message, f"{t('abuse', state.lang)} {_current_question(state, config)}".strip(),
                       Status.COLLECTING.value, record=False)
    if flow.is_foreign_script(message):
        return _finish(state, message, t("foreign", state.lang), Status.COLLECTING.value, record=False)
    if flow.wants_human(message):
        state.needs_human = state.attention = True
        if len(state.followups) < 50:
            state.followups.append({"text": message[:300], "at": time.time()})      # the owner sees what was asked
        owner = (config.get("owner") or {}).get("name") or ("pasukan kami" if state.lang == "ms" else "our team")
        return _finish(state, message, f"{t('handoff', state.lang, owner=owner)} {_current_question(state, config)}".strip(),
                       Status.HUMAN.value, human=True, record=False)
    if flow.wants_cancel(message) and (state.service_checked or state.stage != "job"):
        state.needs_human = state.attention = True
        if len(state.followups) < 50:
            state.followups.append({"text": message[:300], "at": time.time()})
        owner = (config.get("owner") or {}).get("name") or ("pasukan kami" if state.lang == "ms" else "our team")
        return _finish(state, message, t("cancel_noted", state.lang, owner=owner), Status.HUMAN.value, human=True,
                       record=False)
    if state.stage == "done":
        if flow.new_job_intent(message, state):
            flow.start_new_order(state)         # a returning customer: archive the old job, start a new one
        else:
            return _after_done(state, message, config)
    if (flow.is_correction(message) and state.stage in ("contact", "wrapup", "job")) or (
            state.stage in ("contact", "wrapup") and _states_dimension(state, message)):      # after the recap a stated size is final
        fixed = _correct_measurement(state, message)
        if fixed:
            return _after_correction(state, message, config, fixed)
    if state.stage == "contact" and flow.asks_recap(message):
        return _finish(state, message, f"{t('recap_intro', state.lang)}\n{flow.recap(state)}\n\n{contact._prompt(state)}",
                       Status.COLLECTING.value, record=False)
    if state.stage == "contact" and flow._SUPPORTED.search(message) and flow._ANOTHER_ROOM.search(message) \
            and not message.strip().endswith("?"):
        added = _try_add_rooms(state, message, config)
        if added:                                            # "also the kitchen 3x3x2.5": added, then the booking goes on
            return _finish(state, message, f"{added} {contact._prompt(state)}", Status.COLLECTING.value, record=False)
        return _finish(state, message, f"{t('contact_another', state.lang)} {contact._prompt(state)}",
                       Status.COLLECTING.value, record=False)
    if state.stage == "contact" and flow.smalltalk(message) == "thanks":
        return _finish(state, message, f"{t('st_welcome', state.lang)} {contact._prompt(state)}",
                       Status.COLLECTING.value, record=False)
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
        if flow._SUPPORTED.search(message) and flow._ANOTHER_ROOM.search(message) \
                and not message.strip().endswith("?") and not sizes_in(message, loose=True):
            return _finish(state, message, t("wrap_another", state.lang), Status.COLLECTING.value, record=False)
        if flow.is_yes(message):
            state.stage = "done"
            return _finish(state, message, flow.closing_reply(state, config), Status.READY.value)
        faq = flow.faq_answer(message, config, "wrapup", state.lang)
        if faq:                         # a side question: answer it, then ask for the confirmation again
            return _finish(state, message, f"{faq} {t('wrap_ok', state.lang)}", Status.COLLECTING.value,
                           record=False)
        problem = flow.date_problem(message)
        if problem and flow.when_in(message, strict=True):      # a weekend, a holiday or 3 am: never accepted
            return _finish(state, message, t(problem, state.lang), Status.COLLECTING.value, record=False)
        if flow.asks_recap(message) and state.verified:
            return _finish(state, message, f"{t('recap_intro', state.lang)}\n{flow.recap(state)}\n\n{t('wrap_ok', state.lang)}",
                           Status.COLLECTING.value, record=False)
        if ("?" in message or flow._QUESTION_START.match(message)) and not sizes_in(message, loose=True) \
                and not cued_sizes(message):
            owner = (config.get("owner") or {}).get("name") or ("pasukan kami" if state.lang == "ms" else "our team")
            return _finish(state, message, f"{t('faq_other', state.lang, owner=owner)} {t('wrap_ok', state.lang)}",
                           Status.COLLECTING.value, record=False)         # a question we cannot answer is not a "yes"
        state.stage = "job"             # a correction: it goes through the normal flow below

    if persona and geo.foreign_place(message):      # a job outside Malaysia is never quoted, and never stored
        return _finish(state, message, t("location_outside", state.lang), Status.COLLECTING.value, record=False)

    lowered = message.lower()
    if any(k in lowered for k in config.get("inspection_keywords", [])):
        if persona and (sizes_in(message, loose=True) or cued_sizes(message) or flow._SUPPORTED.search(message)):
            state.service_checked = True            # it is a painting job: the details are still taken
            state.needs_human = state.attention = True
            state._faq_prefix = t("inspection_reply", state.lang)
        else:
            return _finish(state, message, t("inspection_reply", state.lang), Status.HUMAN.value, human=True)

    if persona and not state.service_checked:
        service = flow.check_service(message)
        if service == "unknown" and (sizes_in(message, loose=True) or cued_sizes(message)):
            service = "supported"       # sizes mean there is a room to paint, whatever else the message says
        owner = (config.get("owner") or {}).get("name") or ("pasukan kami" if state.lang == "ms" else "our team")
        if service == "unsupported" and not state.declined:
            state.declined = True
            return _finish(state, message, flow.decline_reply(state, config), Status.HUMAN.value, human=True)
        if service != "supported" and state.declined:       # already told it is outside our services: do not repeat it
            return _finish(state, message, t("declined_again", state.lang, owner=owner), Status.HUMAN.value,
                           human=True, record=False)
        if service == "unknown":
            state.service_misses += 1
            kind = flow.smalltalk(message)
            side = flow.faq_answer(message, config, "job", state.lang, force=True)
            question = render(persona_text(persona, "service_question", state.lang), persona, config, state.lang)
            if not side and ("?" in message or flow._QUESTION_START.match(message)) and kind is None:
                side = t("faq_other", state.lang, owner=owner)      # a question we have no fixed answer for
            if side:                                        # a question before any job: answer it, then ask what they need
                reply = f"{side} {question}"
            elif kind and state.service_misses > 1:         # "thanks", "bye", "hello?": answered like a person would
                reply = t(f"st_{kind}", state.lang)
            elif state.service_misses == 1:
                reply = question
            else:                                           # the same question again would be a loop
                reply = t("service_retry", state.lang)
            # kept out of the history so the first real turn still gets the format primer
            return _finish(state, message, reply, Status.COLLECTING.value, record=False)
        state.declined = False
        state.service_checked = True

    nxt = state.next_missing(config)
    if flow.asks_recap(message) and state.verified:
        recap = flow.recap(state)
        return _finish(state, message, f"{t('recap_intro', state.lang)}\n{recap}\n\n{_current_question(state, config)}".strip(),
                       Status.COLLECTING.value, record=False)
    if persona and state.service_checked and nxt and nxt not in ("surface_condition", "address") \
            and flow.smalltalk(message) in ("okay", "confused") and not state.orders and not state.pending_sizes \
            and not state.pending_conflict:
        state.reasks["okay"] = state.reasks.get("okay", 0) + 1
        pick = f"st_ok_{state.reasks['okay'] % 3 + 1}"          # "ok", "hmm", "sure": no answer yet, ask again gently
        return _finish(state, message, f"{t(pick, state.lang)} {ask_for(nxt, state)}", Status.COLLECTING.value,
                       record=False)
    if persona and flow.date_problem(message) and (
            nxt == "preferred_datetime"
            or (len(message.split()) <= 16 and flow.when_in(message, strict=True)
                and not address_in(message))):     # also when they change a date already given
        return _finish(state, message, t(flow.date_problem(message), state.lang), Status.COLLECTING.value, record=False)
    if persona:
        faq = flow.faq_answer(message, config, "job", state.lang)
        if faq and nxt:                 # a side question in the middle of the job: answer, then carry on
            if sizes_in(message, loose=True) or cued_sizes(message):
                state._faq_prefix = faq         # the message also has sizes: answer first, still read them
            else:
                return _finish(state, message, f"{faq} {ask_for(nxt, state)}", Status.COLLECTING.value,
                               record=False)

    if persona and state.next_missing(config) == "paint_tier" and flow.asks_for_ideas(message) \
            and not _TIERS.search(message) and not re.search(r"\byou\s+(pick|choose|decide|select)\b", message, re.I):
        # "which one do you recommend?" is a question, not "no preference": answer it, then ask again
        return _finish(state, message, t("tier_ideas", state.lang), Status.COLLECTING.value, record=False)

    if "colour" in state.missing_required(config) and not (sizes_in(message, loose=True) or cued_sizes(message)) \
            and not re.search(r"\byou\s+(pick|choose|decide|select)\b", message, re.I) \
            and (flow.wants_colour_suggestion(message) or (state.next_missing(config) == "colour"
                                                             and flow.asks_for_ideas(message))):
        return _finish(state, message, t("colour_ideas", state.lang), Status.COLLECTING.value, record=False)
    _resolve_pending_conflict(state, message)
    asked = state.next_missing(config)              # the question the customer is answering
    before, before_estimated = dict(state.verified), list(state.estimated)
    state._rooms_ack = ""
    work = message
    if state.stage == "job":
        added = _try_add_rooms(state, message, config)
        if added:
            state._rooms_ack = added
            work = rooms_module.strip_sizes(message)         # the sizes went to the rooms: do not read them twice
    _swap_answers(state, work, config)
    _prefill_job(state, work, config)
    if not _COUNTED.search(work) or sizes_in(work):          # a number next to "one wall" is a count
        _prefill_measurement(state, work, config)
    rooms_module.fill_heights(state.verified)
    changed = {k for k, v in state.verified.items() if before.get(k) != v}   # read by the backend this turn
    pending = state.pending_sizes
    if pending and not pending["asked"]:        # "12 by 10" with no unit: say what was understood and ask which unit
        pending["asked"] = True
        return _finish(state, message, t("ask_unit", state.lang, a=pending["values"][0], b=pending["values"][1]),
                       Status.COLLECTING.value, record=False)
    system_prompt = load_system_prompt(trade_of(config))
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
            _keep_plain_answer(state, message, asked, result)
        if asked in result.dropped and not result.problems:
            return _ask_again(state, message, config, result, asked, attempt)
        if result.ok:
            return _accept(state, message, config, result, attempt, changed=bool(changed or result.accepted))
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


def _keep_plain_answer(state, message, asked, result):
    """The model did not record the answer to the question it asked (often because it rephrased or
    translated the customer's words, and the check against the message then drops it). A short plain
    reply to a free-text question is kept in the customer's own words: those are grounded by definition."""
    accepted = result.accepted
    limit = _FREE_TEXT.get(asked)
    if not limit or asked in accepted or asked in state.verified or asked in result.dropped:
        return
    text = message.strip()
    words = re.findall(r"[a-z']+", text.lower())
    if not text or "?" in text or len(text) > limit or flow.is_correction(text):
        return
    if asked == "surface_condition" and is_condition(text):
        accepted[asked] = text              # "good", "fine", "ok": a real answer about the surface
        return
    if all(w in _FILLER for w in words):
        if asked in _ASK_AGAIN_KEYS:
            result.dropped.append(asked)        # "yes" is not a condition, a colour or a date
        return
    if asked == "address" and not (re.search(r"\d", text) or len(words) >= 2):
        return
    if not plausible(asked, text, message):
        result.dropped.append(asked)        # a date or a name is not a condition: ask again, do not store it
        return
    accepted[asked] = text


_ASK_AGAIN_KEYS = ("surface_condition", "colour", "preferred_datetime", "address")
_ASK_AGAIN = {"surface_condition": "condition_ask_again", "colour": "colour_ask_again",
              "preferred_datetime": "date_ask_again", "address": "address_ask_again"}
_GIVE_UP = {"surface_condition": ("not described", 2), "colour": ("no preference", 2),
            "preferred_datetime": ("flexible, no specific date", 2), "address": ("to be confirmed with the customer", 3)}


def _ask_again(state, message, config, result, asked, attempt):
    """The reply was not an answer to the question ("bright" for the condition, "yesterday" for the date): ask it
    again with examples. After a couple of tries the field is left open for the owner and the chat moves on."""
    state.reasks[asked] = state.reasks.get(asked, 0) + 1
    placeholder, limit = _GIVE_UP[asked]
    result.soft_problems, result.problems = [], []
    if state.reasks[asked] >= limit:
        result.accepted[asked] = placeholder
        state.attention = state.attention or asked == "address"
        missing = state.missing_required(config, extra=result.accepted)
        result.reply = ask_for(missing[0], state) if missing else ""
        result.status = Status.COLLECTING.value if missing else Status.READY.value
    else:
        if asked == "preferred_datetime" and flow.date_problem(message) in ("date_past", "date_past_year", "date_closed"):
            key = flow.date_problem(message)
        elif asked == "preferred_datetime" and flow._DATE_NEEDS_DAY.search(message):
            key = "date_need_day"
        else:
            key = _ASK_AGAIN[asked]
        result.reply, result.status = t(key, state.lang), Status.COLLECTING.value
    result.dropped = []
    return _accept(state, message, config, result, attempt)


_PRICED = ("room_length_m", "room_width_m", "room_height_m", "extra_rooms", "surfaces", "paint_tier",
           "surface_condition")
_NOTED = ("colour", "preferred_datetime", "address")


def _after_done(state, message, config):
    """The chat is complete and the SME has not (or has) confirmed: answer what matters, stay quiet otherwise.
    A change to the job (another paint, a size, one more room) is applied even after the estimate was approved, and
    the estimate goes back to the owner to approve again at the new price."""
    before = {k: state.verified.get(k) for k in _PRICED + _NOTED}
    before["extra_rooms"] = [dict(r) for r in state.verified.get("extra_rooms") or []] or None
    fixed = _correct_measurement(state, message) if flow.is_correction(message) or _states_dimension(state, message) else None
    if not fixed:
        state.stage = "job"                     # the readers below work on a job in progress
        try:
            _try_add_rooms(state, message, config)
            _swap_answers(state, message, config)
        finally:
            state.stage = "done"
    changed = [k for k in _PRICED + _NOTED if (state.verified.get(k) or None) != (before.get(k) or None)]
    if fixed or changed:
        priced = bool(fixed) or any(k in _PRICED for k in changed)
        owner = (config.get("owner") or {}).get("name") or ("pasukan kami" if state.lang == "ms" else "our team")
        state.attention = True
        if len(state.followups) < 50:
            state.followups.append({"text": message[:300], "at": time.time()})
        if priced and state.quote_status in ("pending_approval", "needs_inspection", "approved", "final"):
            state.quote_stale = True            # re-priced by the service; an approved estimate goes back for approval
        labels = []
        for key in changed:
            label = (t("change_sizes", state.lang) if key.startswith("room_") else
                     t("change_rooms", state.lang) if key == "extra_rooms" else t(f"label_{key}", state.lang))
            value = state.verified.get(key)
            shown = f"{label}: {value}" if isinstance(value, str) else label
            if shown not in labels:
                labels.append(shown)
        if fixed and not labels:
            return _finish(state, message, fixed, Status.READY.value, record=False)
        key = "job_updated" if priced and state.quote_status in ("approved", "final", "pending_approval") else "job_noted"
        return _finish(state, message, t(key, state.lang, changes=", ".join(labels), owner=owner), Status.READY.value,
                       record=False)
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
    # nothing left to ask, or the message said nothing the backend has not already read: no model call is needed
    if state.missing_required(config) and len(_leftover_words(message)) > 1:
        try:
            raw = client.chat(build_messages(config, state, message, None, system_prompt))
            result = validate_response(raw, state, message, config)
            accepted = {k: v for k, v in result.accepted.items() if k not in changed}
        except RunPodError:
            pass
    state.merge(accepted)
    ack = (state._rooms_ack or (t("ack_estimate", state.lang) if estimated
                                else t(_ACKS[(len(state.history) // 2) % len(_ACKS)], state.lang)))
    missing = state.missing_required(config)
    reply = f"{ack} {ask_for(missing[0], state)}" if missing else ""
    done = SimpleNamespace(accepted=accepted, conflicts=[], reply=reply,
                           status=Status.COLLECTING.value if missing else Status.READY.value)
    return _accept(state, message, config, done, 1)


_FILLER_WORDS = {"x", "by", "the", "a", "an", "is", "it", "its", "i", "im", "my", "me", "ok", "okay", "yes", "no",
                 "ya", "please", "pls", "thanks", "thank", "then", "and", "also", "for", "to", "of", "in", "at", "on",
                 "hi", "hello", "hai", "ceiling", "ceilings", "wall", "walls", "one", "only", "just", "long", "wide",
                 "high", "tall", "height", "width", "length", "m", "metre", "metres", "meter", "meters", "cm", "ft",
                 "feet", "dinding", "siling", "tinggi", "lebar", "panjang", "kaki", "meter", "paint", "with", "want",
                 "need", "like", "would", "id", "ill", "can", "you"}


def _leftover_words(message):
    """The words of a message that the backend's own readers did not account for (sizes, tier, colour, time,
    surfaces, filler). Few leftovers means the model has nothing more to extract."""
    text = message.lower()
    for pattern in (_TIERS, _COLOURS, flow._DATE_WORDS, flow._ASAP, flow.NO_PREFERENCE, _WALLS, _WALL, _CEILING):
        text = pattern.sub(" ", text)
    text = re.sub(r"\d+(?:[.,]\d+)?", " ", text)
    return [w for w in re.findall(r"[a-z']+", text) if w not in _FILLER_WORDS and w not in HEDGES
            and w not in ONES and w not in UNIT_FACTORS]


def _greet(state, config, reply):
    """The persona says hello once, in front of the first reply."""
    persona = config.get("persona")
    if not persona or state.greeted:
        return reply
    state.greeted = True
    reply = _HELLO_AGAIN.sub("", reply, count=1)      # the model sometimes says hello again after the persona did
    return f"{greeting_line(persona, config, state.lang)} {reply}".strip()


_HELLO_AGAIN = re.compile(r"^\s*(hi there|hello there|hi|hello|hey|hai)\b[!,.]*\s*", re.I)


def _accept(state, message, config, result, attempt, changed=True):
    state.merge(result.accepted)
    for key in result.accepted:
        if FIELDS[key].kind == "measurement":
            state.last_field = key
    if result.conflicts and (flow.is_correction(message) or flow.SWAP.search(message)):
        for key, _old, new in result.conflicts:     # an explicit "nvm, it's ..." is the answer: no question
            changed = True
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
            if changed:
                state.reasks["wrap_nochange"] = 0
                reply = flow.wrapup_reply(state, config)
            else:                       # the same line again would be a loop: the second time say what is needed
                state.reasks["wrap_nochange"] = state.reasks.get("wrap_nochange", 0) + 1
                if state.reasks["wrap_nochange"] == 1:
                    reply = t("wrap_nochange", state.lang)
                else:
                    state.attention = True
                    reply = t("wrap_stuck", state.lang, owner=flow._owner_for(config, state.lang))
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
_ONE_WALL = re.compile(r"\b(one|1|single|satu)\s+wall\b|\b(a|this|that)\s+wall\b", re.I)
_PHONE_WORD = re.compile(r"\b(phone|number|call|contact|whatsapp|tel|nombor|hubungi)\b", re.I)
_CEILING = re.compile(r"\b(ceilings?|siling)\b", re.I)
_TIERS = re.compile(r"\b(" + "|".join(sorted(TIER_WORDS, key=len, reverse=True)) + r")\b", re.I)
_COLOURS = re.compile(r"\b(" + "|".join(sorted(COLOUR_WORDS, key=len, reverse=True)) + r")\b", re.I)
_COUNTED = re.compile(r"\b(\d+|one|two|three|four|five|satu|dua|tiga|empat|lima)\s*(walls?|ceilings?|rooms?|"
                      r"bedrooms?|coats?|doors?|windows?|dinding|siling|bilik|pintu|tingkap)\b", re.I)
PHOTO_CONDITION = "see the customer's photo"


def changed_keys(before, state):
    return {k for k, v in state.verified.items() if before.get(k) != v}


def _volunteer(state, message):
    """Details mentioned in passing, whatever is being asked: an address, a name, a phone number."""
    if "address" not in state.verified:
        found = address_in(message)
        if found:
            state.verified["address"] = found                   # "... at 5 Jalan Mawar, Taman Melati ..."
    name = explicit_name(message)
    if name:
        state.verified["customer_name"] = name                  # "my name is Ali", "I'm Sarah"
    phone = contact.find_phone(message)
    digits = re.sub(r"\D", "", phone or "")
    if phone and (_PHONE_WORD.search(message) or (len(digits) >= 9 and len(message.split()) <= 6)):
        state.verified["phone"] = phone
        rest = re.sub(r"[+\d\s().\-]{7,}", " ", message).strip(" ,.")
        if rest and len(rest.split()) <= 3 and "customer_name" not in state.verified:
            from .answers import is_name
            if is_name(rest) and re.fullmatch(r"[A-Za-z' ]+", rest):
                state.verified["customer_name"] = rest.title()  # "Siti 0123456789"


def _prefill_job(state, message, config):
    """Answers the backend can read without the model: which surfaces, when, the condition shown in a
    photo, and "no preference". Only the field being asked about (or a clearly stated surface) is filled,
    so a short reply is never lost and the customer is never asked the same thing twice."""
    missing = state.missing_required(config)
    if state.verified.get("surfaces") == ["one wall"] and _WALLS.search(message):
        state.verified["surfaces"] = ["walls"]              # "4 walls each 4x4": it was more than one wall after all
        missing = state.missing_required(config)
    if "surfaces" in missing:
        items = []
        if _WALLS.search(message):
            items.append("walls")
        elif _WALL.search(message):
            # a singular "wall" means one wall (length x height is enough), unless the ceiling is painted too
            items.append("walls" if _CEILING.search(message) and not _ONE_WALL.search(message) else "one wall")
        elif _PLAIN_DINDING.search(message):
            items.append("walls")           # Malay "dinding" with no number: the walls of the room
        if _CEILING.search(message):
            items.append("ceiling")
        if items:
            state.verified["surfaces"] = items
            missing = state.missing_required(config)
    required = set(state.required_fields(config))
    if "surface_condition" in required and "surface_condition" not in state.verified \
            and CONDITION_STRONG.search(message) and "?" not in message:
        state.verified["surface_condition"] = condition_clause(message)    # "paint is peeling and some damp"
    if "paint_tier" in required and "paint_tier" not in state.verified:
        tier = _TIERS.search(message)                   # "Eco", "premium please": said before it was asked
        if tier:
            state.verified["paint_tier"] = TIER_WORDS[tier.group(1).lower()]
    if "colour" in required and "colour" not in state.verified:
        colours = [m.group(1).lower() for m in _COLOURS.finditer(message)]
        if colours:
            state.verified["colour"] = " and ".join(dict.fromkeys(colours))
    if "preferred_datetime" in required and "preferred_datetime" not in state.verified and len(message.split()) > 1:
        when = flow.when_in(message, strict=True)
        if when and not flow.date_problem(message):       # a date that has gone by is asked about, not stored
            state.verified["preferred_datetime"] = when
        elif when:
            state.date_issue = flow.date_problem(message) or ""
    missing = state.missing_required(config)
    if "surface_condition" in missing and state.photo_assessment:
        state.verified["surface_condition"] = PHOTO_CONDITION      # the photo already shows it
        missing = state.missing_required(config)
    if not missing:
        return
    key = missing[0]
    if key == "preferred_datetime":
        when = flow.when_in(message)
        if when and not flow.date_problem(message):
            state.verified[key] = when
        elif when:
            state.date_issue = flow.date_problem(message) or ""
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
    elif key == "address" and state.verified.get("location") and "address" not in state.verified:
        place = state.verified["location"]                     # they already shared where the job is
        state.verified[key] = (" ".join(x for x in (place.get("name"), place.get("address")) if x)
                               or t("pinned", state.lang, lat=place["lat"], lon=place["lon"]))
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
    _, hedged = estimate_in(message)

    def keep(key, value):
        state.verified[key] = value
        state.last_field = key
        if hedged and key not in state.estimated:
            state.estimated.append(key)

    pending = state.pending_sizes
    if pending:                                         # the customer is answering "meters or feet?"
        state.pending_sizes = None
        factors = unit_factors_in(message)
        if not factors and message.strip(" .!").lower() in contact.AFFIRMATIVE and not pending.get("tries"):
            pending["asked"], pending["tries"] = False, 1       # "yes" does not say meters or feet: ask once more
            state.pending_sizes = pending
            return
        if len(factors) == 1:
            factor = next(iter(factors))
            if factor in (1.0, 0.3048):
                state.unit_factor = factor                      # they measure in feet: later plain numbers are feet
            for key, value in zip(pending["keys"], pending["values"]):
                if key in open_fields:
                    converted = round(value * factor, 3)
                    if key == "room_height_m" and converted < 1.5 <= value:
                        converted = float(value)            # "12 x 10 x 3": a 3 ft ceiling is not a room, so it is 3 m
                    keep(key, converted)
            return
    cued = {k: v for k, v in cued_sizes(message).items() if k in open_fields}
    for key, value in cued.items():                     # "height of 3 meters", "4 m long", a square room's perimeter
        keep(key, value)
    open_fields = [k for k in open_fields if k not in cued]
    loose = bool(_COUNT_NOUNS.search(message)) or _bare_number(message) or bool(re.fullmatch(r"[\d\s.,]+", message.strip()))
    sizes = sizes_in(message, loose=loose)
    if sizes and all(n > 0 for n in sizes) and len(open_fields) >= len(sizes):
        # "4 by 5": the next open sizes in order, or in the order the customer named them ("width x length")
        keys = _size_keys(message, open_fields, len(sizes))
        said = unit_factors_in(message)
        if len(said) > 1:
            metric = sizes_metric(message)          # "10ft x 3m": each number has its own unit
            if metric:
                for key, value in zip(keys, metric):
                    keep(key, value)
                return
        if len(said) == 1 and next(iter(said)) in (1.0, 0.3048):
            state.unit_factor = next(iter(said))
        if not said and state.unit_factor != 1.0:
            for key, number in zip(keys, sizes):                # they said feet before: these are feet too
                keep(key, round(number * state.unit_factor, 3))
            return
        if not unit_factors_in(message) and not all(PLAIN_METRES[0] <= n <= PLAIN_METRES[1] for n in sizes):
            if len(sizes) >= 2 and not state.pending_sizes:
                state.pending_sizes = {"keys": keys, "values": sizes, "asked": False}   # "10 by 12": feet or meters?
            return
        text = message if unit_factors_in(message) else f"{message} m"
        try:
            values = [ground_measurement(n, text) for n in sizes]
        except GroundingError:
            return
        for key, value in zip(keys, values):
            keep(key, value)
        return
    if cued:
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
    elif not cued and open_fields and (missing[0] in _CUES or _bare_number(message)):
        key = open_fields[0]            # a bare number is the next size, even if the last question was another one
    else:
        return
    if state.unit_factor != 1.0 and not unit_factors_in(message) and _bare_number(message):
        state.verified[key], state.last_field = round(numbers[0] * state.unit_factor, 3), key
        return                          # they measure in feet
    text = message if unit_factors_in(message) or upper is None else f"{message} m"
    try:
        # the customer is answering this very question, so a plain number is metres ("I said 5")
        assume = ((key == missing[0] or _bare_number(message)) and PLAIN_METRES[0] <= numbers[0] <= PLAIN_METRES[1]
                  and not _COUNT_NOUNS.search(message))
        state.verified[key] = ground_measurement(numbers[0], text, assume_metres=assume)
    except GroundingError:
        return
    state.last_field = key
    if estimated and key not in state.estimated:
        state.estimated.append(key)


_CUE_WORDS = re.compile(r"\b(length|long|panjang|width|wide|lebar|height|tall|high|tinggi)\b", re.I)
_CUE_KEY = {"length": "room_length_m", "long": "room_length_m", "panjang": "room_length_m", "width": "room_width_m",
            "wide": "room_width_m", "lebar": "room_width_m", "height": "room_height_m", "tall": "room_height_m",
            "high": "room_height_m", "tinggi": "room_height_m"}


def _size_keys(message, open_fields, count):
    """Which sizes "3x4" are, in order. "width x length" or "lebar x panjang" names them: the first number is the
    width. Without such words it is length first, then width (then height)."""
    named = []
    for found in _CUE_WORDS.finditer(message):
        key = _CUE_KEY[found.group(1).lower()]
        if key not in named:
            named.append(key)
    if len(named) == count and all(key in open_fields for key in named):
        return named
    return open_fields[:count]


_NOT_NUMBER = re.compile(r"\b(?:not|bukan)\s+\d+(?:[.,]\d+)?\s*(?:m|meters?|metres?|cm|ft|feet|kaki)?\b", re.I)


def _states_dimension(state, message):
    """"the height is 5 m", "it's 5m tall": one number, a unit and one dimension word for a size already stored. The
    customer is stating the right value, so it replaces the old one even without a "nvm" or "actually"."""
    if "?" in message:
        return False
    upper, _ = estimate_in(message)
    numbers = [upper] if upper is not None else numbers_in(message)
    if len(numbers) != 1 or not unit_factors_in(message):
        return False
    words = set(re.findall(r"[a-z]+", message.lower()))
    cued = [k for k in _CUES if _CUES[k] & words]
    return len(cued) == 1 and cued[0] in state.verified


def _correct_measurement(state, message):
    """"nvm its 4m": replace the measurement the customer gave last (or the one they name). Returns the
    acknowledgement, or None when the message is not a clear correction of a size."""
    message = _NOT_NUMBER.sub(" ", message)             # "its 2.7 not 5": the number after "not" is the wrong one
    if flow._DATE_WORDS.search(message) and not unit_factors_in(message) \
            and not any(_CUES[k] & set(re.findall(r"[a-z]+", message.lower())) for k in _CUES):
        return None                                      # "actually 3 am Sunday": a new time, not a new size
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
        if state.unit_factor != 1.0 and not unit_factors_in(message):
            value = round(numbers[0] * state.unit_factor, 3)
        else:
            value = ground_measurement(numbers[0], text, assume_metres=PLAIN_METRES[0] <= numbers[0] <= PLAIN_METRES[1])
    except GroundingError:
        return None
    state.verified[key], state.last_field = value, key
    if estimated and key not in state.estimated:
        state.estimated.append(key)
    elif not estimated and key in state.estimated:
        state.estimated.remove(key)
    return t("ack_fixed", state.lang, label=t(f"label_{key}", state.lang), value=metres(value, state.lang))


_PLACEHOLDERS = {"no preference", "i dont know", "i don't know", "any", "not described"}


def _swap_answers(state, message, config):
    """A new answer to something already answered replaces it when the customer is plainly changing their mind
    ("actually premium", "change colour to blue", "make it Saturday", "sorry I meant 5 x 5")."""
    if "?" in message and not re.search(r"\b(change|switch|make it|instead|tukar|ubah)\b", message, re.I):
        return
    v, short = state.verified, len(message.split()) <= 4
    swap = bool(flow.SWAP.search(message) or flow.is_correction(message))
    tiers = {TIER_WORDS[m.group(1).lower()] for m in _TIERS.finditer(message)}
    if len(tiers) == 1 and "paint_tier" in v and v["paint_tier"] not in tiers and v["paint_tier"] != "no preference" \
            and (swap or short):
        v["paint_tier"] = next(iter(tiers))
    elif len(tiers) == 1 and v.get("paint_tier") == "no preference":
        v["paint_tier"] = next(iter(tiers))
    colours = list(dict.fromkeys(m.group(1).lower() for m in _COLOURS.finditer(message)))
    if colours and "colour" in v:
        new, old = " and ".join(colours), str(v["colour"]).lower()
        if new != old and (swap or short or old in _PLACEHOLDERS or not _COLOURS.search(old)):
            v["colour"] = new
    if "preferred_datetime" in v:
        when = flow.when_in(message, strict=True)
        if when and when != v["preferred_datetime"] and (swap or short) and not flow.date_problem(message):
            v["preferred_datetime"] = when
    _swap_surfaces(state, message, swap)
    sized = sizes_in(message)
    swap = swap or bool(sized and unit_factors_in(message))        # "4 meters by 3 meters" said again: they mean it
    if not swap:
        return
    keys = [k for k in ("room_length_m", "room_width_m", "room_height_m") if k in v]
    if single_wall(v.get("surfaces")):
        keys = [k for k in keys if k != "room_width_m"]
    sizes = sizes_in(message)
    if sizes and all(n > 0 for n in sizes) and 2 <= len(sizes) <= 3 and len(keys) >= len(sizes):
        order = ["room_length_m", "room_width_m", "room_height_m"]
        if single_wall(v.get("surfaces")):
            order = ["room_length_m", "room_height_m"]
        said = unit_factors_in(message)
        plain = all(PLAIN_METRES[0] <= n <= PLAIN_METRES[1] for n in sizes)
        if said or plain or state.unit_factor != 1.0:
            factor = next(iter(said)) if len(said) == 1 else state.unit_factor
            for key, number in zip(_size_keys(message, order, len(sizes)), sizes):
                v[key] = round(number * factor, 3)
                state.last_field = key
            return
    for key, value in cued_sizes(message).items():
        if key in v and abs(v[key] - value) > 0.01:
            v[key], state.last_field = value, key


_ADD = re.compile(r"\b(also|too|as well|plus|and|add|juga|pun|dan|tambah)\b", re.I)
_ONLY = re.compile(r"\b(only|just|instead|change|switch|sahaja|saja|tukar|ubah)\b", re.I)
_BOTH = re.compile(r"\b(both|semua sekali|dua-dua|kedua-dua)\b", re.I)


def _swap_surfaces(state, message, swap):
    """"actually both", "and also the ceiling", "change it to ceiling": the surfaces to paint change."""
    current = list(state.verified.get("surfaces") or [])
    if not current:
        return
    if _BOTH.search(message):
        state.verified["surfaces"] = ["walls", "ceiling"]
        return
    ceiling, walls = bool(_CEILING.search(message)), bool(_WALLS.search(message) or _WALL.search(message))
    has_ceiling = any("ceil" in str(s).lower() for s in current)
    has_walls = any("wall" in str(s).lower() for s in current)
    if ceiling and not walls and not has_ceiling:
        if _ADD.search(message) and not _ONLY.search(message):
            state.verified["surfaces"] = current + ["ceiling"]
        elif _ONLY.search(message) or swap:
            state.verified["surfaces"] = ["ceiling"]
    elif walls and not ceiling and not has_walls:
        if _ADD.search(message) and not _ONLY.search(message):
            state.verified["surfaces"] = current + ["walls"]
        elif _ONLY.search(message) or swap:
            state.verified["surfaces"] = ["walls"]


def advance(state, config, message, ack=""):
    """Carry on after the backend filled a field itself (a shared location answering the address): acknowledge,
    then ask the next question, or move on to the contact step when the job is complete."""
    missing = state.missing_required(config)
    reply = f"{ack} {ask_for(missing[0], state)}".strip() if missing else ack
    done = SimpleNamespace(accepted={}, conflicts=[], reply=reply,
                           status=Status.COLLECTING.value if missing else Status.READY.value)
    return _accept(state, message, config, done, 1).reply


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


def _try_add_rooms(state, message, config):
    """Rooms named in the message: "the master bedroom is 4 by 5 by 3 and the kids room is 3 by 3 by 3", "3 bedrooms
    each 4x4", "also the kitchen 3x3x2.5", "same size for the other bedroom". The first room fills the usual size
    fields while they are open; every other room is kept in verified["extra_rooms"]. Returns the acknowledgement."""
    v = state.verified
    open_sizes = [k for k in state.missing_required(config) if k in _CUES]
    found = rooms_module.sized_rooms(message, state)
    count = rooms_module.copies(message)
    new = []
    if found and count and len(found) == 1:
        label = found[0]["name"]
        new = [dict(found[0], name=(f"{label} {i}" if label else "")) for i in range(1, count + 1)]
    elif len(found) >= 2:
        new = found
    elif len(found) == 1 and not open_sizes and not rooms_module.is_correction(message):
        label = found[0]["name"]
        if rooms_module.adds_room(message) or (label and v.get("room_name") and label != v["room_name"]):
            new = found                                     # one more room after the first
    elif not found and not open_sizes and rooms_module.wants_same_again(message):
        last = (v.get("extra_rooms") or [None])[-1] or {k: v.get(k) for k in
                                                         ("room_length_m", "room_width_m", "room_height_m")}
        new = [dict(last, name=rooms_module.label_of(message))]
    if not new:
        return ""
    if open_sizes and len(new) >= 2:                         # the first room is the job's own room
        first, new = new[0], new[1:]
        for key in ("room_length_m", "room_width_m", "room_height_m"):
            if key in open_sizes and first.get(key) is not None:
                v[key] = first[key]
                state.last_field = key
        if first.get("name"):
            v["room_name"] = first["name"]
    elif open_sizes:
        return ""
    extras = v.setdefault("extra_rooms", [])
    for room in new:
        if not any(all(room.get(k) == e.get(k) for k in room) for e in extras):
            extras.append(room)
    if not extras:
        v.pop("extra_rooms")
    rooms_module.fill_heights(v)
    return t("rooms_noted", state.lang, count=1 + len(extras))


def _finish(state, message, reply, status, human=False, extracted=None, record=True):
    rooms_module.fill_heights(state.verified)
    if state.lang == "en":
        reply = us_spelling(reply)              # "meters" even when the model writes "metres"
    if record:
        state.add_turn(message, reply, status, extracted)
    state.status = status
    state.needs_human = state.needs_human or human
    return TurnResult(reply=reply, status=status)
