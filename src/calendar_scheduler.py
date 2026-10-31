"""
calendar_scheduler.py
─────────────────────
Auto-calendar booking function:
  1. Takes HOURS of work needed (and optional start date, defaults to today/now).
  2. Scans through the calendar to find the FIRST available time window that
     is long enough for the task.
  3. Asks the BUSINESS OWNER first: "Slot found. Do you accept?"
  4. If owner accepts → asks the CLIENT: "Does this time work for you?"
  5. If EITHER owner or client declines → immediately searches for the NEXT
     open slot and repeats the approval loop.
  6. When both accept → re-checks availability (double-booking guard) and books it.

Supports:
  - MockCalendar  (for testing without Google account)
  - GoogleCalendar (real Google Calendar via service account JSON)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Callable, Optional, Protocol


def _load_env_file():
    """Load key-value pairs from .env into os.environ if not already set."""
    for env_name in (".env", os.path.join(os.path.dirname(__file__), ".env")):
        if os.path.exists(env_name):
            try:
                with open(env_name, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            except Exception:
                pass
            break


_load_env_file()

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Asia/Kuala_Lumpur")
except Exception:
    from datetime import timezone
    TZ = timezone(timedelta(hours=8))


# ─── 1. Working Rules ────────────────────────────────────────────────────
@dataclass
class WorkingRules:
    day_start: time = time(9, 0)
    day_end: time = time(18, 0)
    working_days: tuple = (0, 1, 2, 3, 4)  # Mon=0 .. Fri=4; weekends are closed
    step_minutes: int = 30       # search granularity (every 30 mins)
    buffer_minutes: int = 0      # gap required around events
    search_days: int = 14        # how many days ahead to search


RULES = WorkingRules()


# ─── 2. Calendar Backends ────────────────────────────────────────────────
class CalendarBackend(Protocol):
    def get_busy(self, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]: ...
    def book(self, start: datetime, end: datetime, title: str, description: str = "") -> str: ...


class MockCalendar:
    """In-memory calendar for testing without needing Google credentials."""

    def __init__(self, busy: Optional[list[tuple[datetime, datetime]]] = None):
        self.busy = list(busy or [])
        self.events: list[dict] = []

    def get_busy(self, start: datetime, end: datetime):
        return [(s, e) for s, e in self.busy if s < end and e > start]

    def book(self, start: datetime, end: datetime, title: str, description: str = ""):
        self.busy.append((start, end))
        self.events.append({"start": start, "end": end, "title": title, "description": description})
        return f"mock-{len(self.events)}"


class GoogleCalendar:
    """
    Real Google Calendar connection via OAuth 2.0 or Service Account.

    Supports:
      - OAuth 2.0 credentials.json (Desktop client, opens browser once, saves token.json)
      - Service Account service_account.json (server-to-server)
    """
    SCOPES = ["https://www.googleapis.com/auth/calendar"]

    def __init__(
        self,
        credentials_file: Optional[str] = None,
        calendar_id: Optional[str] = None,
        token_file: Optional[str] = None
    ):
        import json
        from googleapiclient.discovery import build

        credentials_file = credentials_file or os.environ.get("GOOGLE_CALENDAR_CREDENTIALS", "credentials.json")
        calendar_id = calendar_id or os.environ.get("GOOGLE_CALENDAR_ID", "primary")
        token_file = token_file or os.environ.get("GOOGLE_CALENDAR_TOKEN", "token.json")

        creds = None
        if os.path.exists(token_file):
            from google.oauth2.credentials import Credentials
            try:
                creds = Credentials.from_authorized_user_file(token_file, self.SCOPES)
            except Exception:
                creds = None

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                from google.auth.transport.requests import Request
                creds.refresh(Request())
            else:
                client_id = os.environ.get("GOOGLE_CLIENT_ID")
                client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")

                if os.path.exists(credentials_file):
                    with open(credentials_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                elif client_id and client_secret:
                    data = {
                        "installed": {
                            "client_id": client_id,
                            "client_secret": client_secret,
                            "project_id": os.environ.get("GOOGLE_PROJECT_ID", "orbyte-calendar"),
                            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                            "token_uri": "https://oauth2.googleapis.com/token",
                            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                            "redirect_uris": ["http://localhost"]
                        }
                    }
                else:
                    raise FileNotFoundError(f"Missing {credentials_file} and no GOOGLE_CLIENT_ID/SECRET in .env.")

                if "installed" in data or "web" in data:
                    from google_auth_oauthlib.flow import InstalledAppFlow
                    if os.path.exists(credentials_file):
                        flow = InstalledAppFlow.from_client_secrets_file(credentials_file, self.SCOPES)
                    else:
                        flow = InstalledAppFlow.from_client_config(data, self.SCOPES)
                    print("\n[Google Calendar] Opening browser to authenticate with your Google account...")
                    creds = flow.run_local_server(port=0)
                    with open(token_file, "w", encoding="utf-8") as tf:
                        tf.write(creds.to_json())
                    print("[Google Calendar] Authentication successful! Saved to token.json.")
                else:
                    from google.oauth2 import service_account
                    creds = service_account.Credentials.from_service_account_file(
                        credentials_file, scopes=self.SCOPES
                    )

        self.service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        self.calendar_id = calendar_id

    def get_busy(self, start: datetime, end: datetime):
        body = {
            "timeMin": start.isoformat(),
            "timeMax": end.isoformat(),
            "timeZone": str(TZ),
            "items": [{"id": self.calendar_id}],
        }
        resp = self.service.freebusy().query(body=body).execute()
        busy = resp["calendars"][self.calendar_id].get("busy", [])
        return [
            (
                datetime.fromisoformat(b["start"].replace("Z", "+00:00")).astimezone(TZ),
                datetime.fromisoformat(b["end"].replace("Z", "+00:00")).astimezone(TZ),
            )
            for b in busy
        ]

    def book(self, start: datetime, end: datetime, title: str, description: str = ""):
        event = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start.isoformat(), "timeZone": str(TZ)},
            "end": {"dateTime": end.isoformat(), "timeZone": str(TZ)},
        }
        created = self.service.events().insert(calendarId=self.calendar_id, body=event).execute()
        return created["id"]


# ─── 3. Availability & Slot Finding Logic ─────────────────────────────────
def _overlaps(busy, start: datetime, end: datetime, buffer_minutes: int) -> bool:
    b = timedelta(minutes=buffer_minutes)
    return any(bs < end + b and be > start - b for bs, be in busy)


def _within_working_hours(start: datetime, end: datetime, rules: WorkingRules) -> bool:
    return (
        start.weekday() in rules.working_days
        and start.date() == end.date()
        and start.time() >= rules.day_start
        and end.time() <= rules.day_end
    )


def _validate_hours(hours: float, rules: WorkingRules) -> None:
    day_len = (
        datetime.combine(datetime.min, rules.day_end) - datetime.combine(datetime.min, rules.day_start)
    ).total_seconds() / 3600
    if hours <= 0:
        raise ValueError("hours must be greater than 0")
    if hours > day_len:
        raise ValueError(
            f"{hours}h exceeds one working day ({day_len}h). Split multi-day jobs into blocks."
        )


def is_free(
    calendar: CalendarBackend,
    start: datetime,
    hours: float,
    rules: WorkingRules = RULES,
    now: Optional[datetime] = None
) -> bool:
    """True if [start, start + hours] is within working hours and has no conflicts."""
    _validate_hours(hours, rules)
    now = now or datetime.now(TZ)
    end = start + timedelta(hours=hours)
    if start <= now or not _within_working_hours(start, end, rules):
        return False
    pad = timedelta(minutes=rules.buffer_minutes)
    busy = calendar.get_busy(start - pad, end + pad)
    return not _overlaps(busy, start, end, rules.buffer_minutes)


def find_next_available_slot(
    calendar: CalendarBackend,
    hours: float,
    start_from: datetime,
    rules: WorkingRules = RULES,
    exclude: tuple = (),
    now: Optional[datetime] = None,
) -> Optional[datetime]:
    """
    Scans the calendar forward starting from start_from to find the FIRST
    available slot that has enough continuous free time for the task.
    """
    _validate_hours(hours, rules)
    now = now or datetime.now(TZ)
    search_start = max(start_from, now)

    first_day = search_start.date()
    last_day = first_day + timedelta(days=rules.search_days)

    # Fetch all busy blocks in the search window at once
    busy = calendar.get_busy(
        datetime.combine(first_day, time.min, TZ),
        datetime.combine(last_day, time.max, TZ),
    )

    dur = timedelta(hours=hours)
    step = timedelta(minutes=rules.step_minutes)

    day = first_day
    while day <= last_day:
        if day.weekday() in rules.working_days:
            # On the first day, don't search earlier than search_start
            day_work_start = datetime.combine(day, rules.day_start, TZ)
            day_work_end = datetime.combine(day, rules.day_end, TZ)

            if day == first_day and search_start > day_work_start:
                s = search_start
                # Round up to next step
                remainder = s.minute % rules.step_minutes
                if remainder != 0:
                    s += timedelta(minutes=rules.step_minutes - remainder)
                s = s.replace(second=0, microsecond=0)
            else:
                s = day_work_start

            while s + dur <= day_work_end:
                if (
                    s > now
                    and s not in exclude
                    and not _overlaps(busy, s, s + dur, rules.buffer_minutes)
                ):
                    return s
                s += step

        day += timedelta(days=1)

    return None


# ─── 4. Main Scheduling Function ──────────────────────────────────────────
@dataclass
class BookingResult:
    status: str                      # "booked" | "no_slot_found"
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    event_id: Optional[str] = None
    log: list = field(default_factory=list)


def schedule_job(
    hours: float,
    calendar: CalendarBackend,
    ask_owner: Callable[[datetime, datetime], bool],
    ask_client: Callable[[datetime, datetime], tuple[bool, Optional[datetime]]],
    *,
    start_from: Optional[datetime] = None,
    job_title: str = "Painting Job",
    customer_name: str = "Customer",
    rules: WorkingRules = RULES,
    max_attempts: int = 10,
) -> BookingResult:
    """
    1. Scans calendar for first slot fitting `hours`.
    2. Asks OWNER: if declined, skips whole block (no +30m nudge), jumps past slot.
    3. Asks CLIENT: if declined, client can suggest preferred date.
    4. Re-checks availability before booking.
    5. Books appointment.
    """
    _validate_hours(hours, rules)
    now = datetime.now(TZ)
    search_cursor = start_from or now
    if search_cursor.tzinfo is None:
        search_cursor = search_cursor.replace(tzinfo=TZ)

    result = BookingResult(status="no_slot_found")
    rejected_ranges: list[tuple[datetime, datetime]] = []
    dur = timedelta(hours=hours)

    result.log.append(f"Search started for {hours}h job from {search_cursor:%a %d %b %Y, %H:%M}.")

    for attempt in range(1, max_attempts + 1):
        slot = find_next_available_slot(
            calendar=calendar,
            hours=hours,
            start_from=search_cursor,
            rules=rules,
            exclude=tuple(r[0] for r in rejected_ranges),
            now=now,
        )

        # Skip slots overlapping with previously owner-rejected blocks
        while slot and any(r[0] <= slot < r[1] or slot <= r[0] < slot + dur for r in rejected_ranges):
            search_cursor = max(r[1] for r in rejected_ranges if r[0] <= slot < r[1] or slot <= r[0] < slot + dur)
            slot = find_next_available_slot(
                calendar=calendar,
                hours=hours,
                start_from=search_cursor,
                rules=rules,
                exclude=tuple(r[0] for r in rejected_ranges),
                now=now,
            )

        if not slot:
            result.log.append(f"No free {hours}h slot in {rules.search_days} days.")
            break

        end = slot + dur
        result.log.append(f"Proposed: {slot:%a %d %b %H:%M}–{end:%H:%M} ({hours}h).")

        # Owner decision
        if not ask_owner(slot, end):
            result.log.append(f"Owner declined {slot:%a %d %b %H:%M}–{end:%H:%M}. Skipping entire block.")
            rejected_ranges.append((slot, end))
            # Smart jump: don't nudge 30m. Jump past this entire slot
            search_cursor = end
            continue

        result.log.append(f"Owner approved {slot:%a %d %b %H:%M}.")

        # Client decision + counter-proposal
        client_ok, client_pref = ask_client(slot, end)
        if not client_ok:
            if client_pref:
                result.log.append(f"Client declined. Requested instead: {client_pref:%a %d %b %H:%M}.")
                search_cursor = client_pref
            else:
                result.log.append(f"Client declined. Auto-searching next open day.")
                rejected_ranges.append((slot, end))
                search_cursor = end
            continue

        result.log.append(f"Client approved {slot:%a %d %b %H:%M}.")

        # Double-booking guard
        if not is_free(calendar, slot, hours, rules, now):
            result.log.append(f"Slot {slot:%a %d %b %H:%M} taken during chat. Retrying...")
            rejected_ranges.append((slot, end))
            search_cursor = end
            continue

        # Book
        event_id = calendar.book(
            start=slot,
            end=end,
            title=f"{job_title} - {customer_name}",
            description=f"Auto-booked. Duration: {hours}h."
        )
        result.status = "booked"
        result.start = slot
        result.end = end
        result.event_id = event_id
        result.log.append(f"Booked: {slot:%a %d %b %Y, %H:%M}–{end:%H:%M} (ID: {event_id})")
        return result

    return result


# ─── Helper for AI Agent / CLI Input ─────────────────────────────────────
def parse_date(value: str) -> datetime:
    """Accepts 'YYYY-MM-DD HH:MM' or 'YYYY-MM-DD' (defaults to 09:00)."""
    value = value.strip()
    try:
        dt = datetime.strptime(value, "%Y-%m-%d %H:%M")
    except ValueError:
        d = datetime.strptime(value, "%Y-%m-%d")
        dt = datetime.combine(d.date(), RULES.day_start)
    return dt.replace(tzinfo=TZ)


# ─── Interactive CLI Helpers ─────────────────────────────────────────────
def _console_yes_no(prompt: str) -> bool:
    while True:
        resp = input(f"{prompt} [y/n]: ").strip().lower()
        if resp in ("y", "yes"):
            return True
        if resp in ("n", "no"):
            return False
        print("Please enter 'y' for yes or 'n' for no.")


def console_owner(start: datetime, end: datetime) -> bool:
    return _console_yes_no(f"\n[BUSINESS OWNER] Can you do the job on {start:%A %d %b %Y, %H:%M}–{end:%H:%M}?")


def console_client(start: datetime, end: datetime) -> tuple[bool, Optional[datetime]]:
    ok = _console_yes_no(f"[CLIENT] Is {start:%A %d %b %Y, %H:%M}–{end:%H:%M} good for you?")
    if ok:
        return True, None
    raw = input("  [CLIENT] What date/time do you prefer? (YYYY-MM-DD HH:MM or Enter to skip): ").strip()
    if raw:
        try:
            return False, parse_date(raw)
        except Exception:
            print("  [CLIENT] Invalid format. Will auto-search next available.")
    return False, None


# ═════════════════════════════════════════════════════════════════════════
# INTERACTIVE DEMO TEST
# ═════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 60)
    print("      CALENDAR AUTO-SCHEDULER — INTERACTIVE DEMO")
    print("=" * 60)

    # 1. Connect Google Calendar (Mandatory)
    print("\n[Connecting] Initializing Google Calendar...")
    cal = GoogleCalendar()
    print("[✓] Connected to Google Calendar.")

    # 2. Get Input from User
    print("\n--- Enter Job Details ---")
    hours_input = float(input("Number of work hours needed (e.g. 3.5): ").strip())

    date_input = input("Search starting from date (YYYY-MM-DD) [press Enter for today]: ").strip()
    if date_input:
        search_start = parse_date(date_input)
    else:
        search_start = datetime.now(TZ)

    print(f"\n--> Scanning calendar starting from {search_start:%A %d %b %Y, %H:%M} for a {hours_input}h slot...\n")

    # 3. Run the Scheduling Function
    result = schedule_job(
        hours=hours_input,
        calendar=cal,
        ask_owner=console_owner,
        ask_client=console_client,
        start_from=search_start,
        job_title="Painting Service",
        customer_name="Omar",
    )

    # 4. Display Results
    print("\n" + "=" * 60)
    print("                    FINAL RESULT")
    print("=" * 60)
    print("\nActivity Log Trail:")
    for step in result.log:
        print(f"  * {step}")

    if result.status == "booked":
        print(f"\n[✓] APPOINTMENT BOOKED!")
        print(f"    Date/Time : {result.start:%A %d %b %Y, %H:%M} – {result.end:%H:%M}")
        print(f"    Event ID  : {result.event_id}")
    else:
        print(f"\n[✗] Could not find an accepted slot.")
