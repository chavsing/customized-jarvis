"""
Gmail Brief — Fetches and summarizes important emails from the last 24 hours.

Uses the Google Gmail API with OAuth2. On first run, opens a browser for
the user to authorize access. The refresh token is saved for subsequent runs.

Credentials file: config/google_credentials.json  (OAuth2 client secrets)
Token file:       config/gmail_token.json        (saved refresh token)
"""

import json
import sys
import os
from datetime import datetime, timedelta, timezone
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

CONFIG_DIR    = _base_dir() / "config"
CREDS_PATH    = CONFIG_DIR / "google_credentials.json"
TOKEN_PATH    = CONFIG_DIR / "gmail_token.json"
SCOPES        = ["https://www.googleapis.com/auth/gmail.readonly"]


# ── OAuth2 ─────────────────────────────────────────────────────

def _get_service():
    """Authenticate and return a Gmail API service instance."""
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

        # Save token for next time
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

    return build("gmail", "v1", credentials=creds, cache_discovery=False)


# ── email fetching ─────────────────────────────────────────────

def _build_query(hours: int = 24) -> str:
    """Build a Gmail search query for important recent emails."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    after_ts = int(since.timestamp())
    # is:unread + after timestamp + importance markers
    return f"is:unread after:{after_ts}"


def _fetch_important(service, hours: int = 24, max_results: int = 15) -> list[dict]:
    """Fetch important emails from the last N hours."""
    query = _build_query(hours)
    results = service.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()

    messages = results.get("messages", [])
    if not messages:
        return []

    emails = []
    for msg_ref in messages:
        try:
            msg = service.users().messages().get(
                userId="me", id=msg_ref["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"]
            ).execute()
        except HttpError:
            continue

        headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}

        # Parse sender name/email
        from_raw = headers.get("from", "Unknown Sender")
        # "Name <email>" → "Name"
        sender = from_raw.split("<")[0].strip().strip('"') or from_raw

        subject = headers.get("subject", "(No subject)")
        snippet  = msg.get("snippet", "")[:120]
        is_starred = "STARRED" in msg.get("labelIds", [])
        is_important = "IMPORTANT" in msg.get("labelIds", [])

        emails.append({
            "sender": sender,
            "subject": subject,
            "snippet": snippet,
            "starred": is_starred,
            "important": is_important,
            "unread": "UNREAD" in msg.get("labelIds", []),
        })

    # Sort: starred first, then important, then rest
    emails.sort(key=lambda e: (not e["starred"], not e["important"]))
    return emails


# ── formatting ─────────────────────────────────────────────────

def _format_brief(emails: list[dict]) -> str:
    """Format email list into a JARVIS-style spoken brief."""
    if not emails:
        return "You have no unread emails, sir. Your inbox is clear."

    total = len(emails)
    starred = [e for e in emails if e["starred"]]
    important = [e for e in emails if e["important"] and not e["starred"]]
    regular = [e for e in emails if not e["starred"] and not e["important"]]

    parts = [f"You have {total} unread email{'s' if total != 1 else ''}."]

    idx = 1
    if starred:
        parts.append(f"\n{len(starred)} starred:")
        for e in starred[:3]:
            parts.append(f"  {idx}. From {e['sender']} — \"{e['subject']}\"")
            idx += 1

    if important:
        parts.append(f"\n{len(important)} important:")
        for e in important[:3]:
            parts.append(f"  {idx}. From {e['sender']} — \"{e['subject']}\"")
            idx += 1

    if regular and idx <= 5:
        remaining = 6 - idx
        if remaining > 0:
            parts.append(f"\nAnd {len(regular)} other{'s' if len(regular) != 1 else ''}:")
            for e in regular[:remaining]:
                parts.append(f"  {idx}. From {e['sender']} — \"{e['subject']}\"")
                idx += 1

    return "\n".join(parts)


# ── public action ──────────────────────────────────────────────

def gmail_brief(parameters: dict, player=None, session_memory=None) -> str:
    """Fetch and summarize important emails for the morning brief.

    Parameters:
        hours (int): How many hours back to look (default 24).
        max_results (int): Max emails to fetch (default 15).
    """
    hours       = int(parameters.get("hours", 24))
    max_results = int(parameters.get("max_results", 15))

    try:
        service = _get_service()
    except FileNotFoundError as e:
        msg = f"Sir, Gmail is not configured. {e}"
        _log(msg, player)
        return msg
    except Exception as e:
        msg = f"Sir, I couldn't connect to Gmail: {e}"
        _log(msg, player)
        return msg

    try:
        emails = _fetch_important(service, hours=hours, max_results=max_results)
    except Exception as e:
        msg = f"Sir, I encountered an error fetching emails: {e}"
        _log(msg, player)
        return msg

    result = _format_brief(emails)
    _log(result, player)
    return result


def _log(message: str, player=None):
    print(f"[GmailBrief] {message}")
    if player:
        try:
            player.write_log(f"JARVIS: {message}")
        except Exception:
            pass
