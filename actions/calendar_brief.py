"""
Calendar Brief — Fetches today's appointments from Google Calendar.

Uses the Google Calendar API with OAuth2. Shares the same OAuth credentials
as the Gmail brief module. Only needs read-only access.

Credentials file: config/google_credentials.json  (OAuth2 client secrets)
Token file:       config/calendar_token.json      (saved refresh token)
"""

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


# ── paths ──────────────────────────────────────────────────────

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

CONFIG_DIR = _base_dir() / "config"
CREDS_PATH = CONFIG_DIR / "google_credentials.json"
TOKEN_PATH = CONFIG_DIR / "calendar_token.json"
SCOPES     = ["https://www.googleapis.com/auth/calendar.readonly"]


# ── OAuth2 ─────────────────────────────────────────────────────

def _get_service():
    """Authenticate and return a Calendar API service instance."""
    creds = None

    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None

        if not creds:
            if not CREDS_PATH.exists():
                raise FileNotFoundError(
                    f"Google OAuth credentials not found at {CREDS_PATH}. "
                    "Download credentials.json from Google Cloud Console and place it in config/."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)

        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

    return build("calendar", "v3", credentials=creds, cache_discovery=False)


# ── event fetching ─────────────────────────────────────────────

def _get_today_bounds():
    """Return (start_utc_iso, end_utc_iso) for today in the local timezone."""
    local_tz = datetime.now().astimezone().tzinfo
    now_local = datetime.now(local_tz)
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local   = now_local.replace(hour=23, minute=59, second=59, microsecond=0)

    start_utc = start_local.astimezone(timezone.utc).isoformat()
    end_utc   = end_local.astimezone(timezone.utc).isoformat()
    return start_utc, end_utc


def _fetch_today_events(service, max_results: int = 20) -> list[dict]:
    """Fetch today's calendar events."""
    time_min, time_max = _get_today_bounds()

    try:
        events_result = service.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
    except HttpError as e:
        raise RuntimeError(f"Calendar API error: {e}")

    events = events_result.get("items", [])
    if not events:
        return []

    parsed = []
    for event in events:
        start = event["start"].get("dateTime", event["start"].get("date", ""))
        end   = event["end"].get("dateTime", event["end"].get("date", ""))

        # Parse time
        start_time = _format_time(start)
        end_time   = _format_time(end) if end else ""

        summary = event.get("summary", "(No title)")
        location = event.get("location", "")
        organizer = event.get("organizer", {}).get("email", "")
        is_all_day = "date" in event["start"]  # all-day events have "date" not "dateTime"

        parsed.append({
            "summary": summary,
            "start": start_time,
            "end": end_time,
            "location": location,
            "organizer": organizer,
            "all_day": is_all_day,
        })

    return parsed


def _format_time(iso_str: str) -> str:
    """Convert ISO datetime to human-readable time like '10:30 AM'."""
    try:
        if "T" in iso_str:
            dt = datetime.fromisoformat(iso_str)
            return dt.strftime("%I:%M %p").lstrip("0")
        return iso_str  # date-only (all-day)
    except Exception:
        return iso_str


# ── formatting ─────────────────────────────────────────────────

def _format_brief(events: list[dict]) -> str:
    """Format event list into a JARVIS-style spoken brief."""
    if not events:
        return "You have no appointments today, sir. Your schedule is clear."

    total = len(events)
    parts = [f"You have {total} appointment{'s' if total != 1 else ''} today."]

    for i, ev in enumerate(events, 1):
        time_str = "All day" if ev["all_day"] else ev["start"]
        line = f"  {i}. {time_str} — {ev['summary']}"
        if ev["location"]:
            line += f" at {ev['location']}"
        parts.append(line)

    return "\n".join(parts)


# ── public action ──────────────────────────────────────────────

def calendar_brief(parameters: dict, player=None, session_memory=None) -> str:
    """Fetch and summarize today's calendar events for the morning brief.

    Parameters:
        max_results (int): Max events to fetch (default 20).
    """
    max_results = int(parameters.get("max_results", 20))

    try:
        service = _get_service()
    except FileNotFoundError as e:
        msg = f"Sir, Google Calendar is not configured. {e}"
        _log(msg, player)
        return msg
    except Exception as e:
        msg = f"Sir, I couldn't connect to Google Calendar: {e}"
        _log(msg, player)
        return msg

    try:
        events = _fetch_today_events(service, max_results=max_results)
    except Exception as e:
        msg = f"Sir, I encountered an error fetching your calendar: {e}"
        _log(msg, player)
        return msg

    result = _format_brief(events)
    _log(result, player)
    return result


def _log(message: str, player=None):
    print(f"[CalendarBrief] {message}")
    if player:
        try:
            player.write_log(f"JARVIS: {message}")
        except Exception:
            pass
