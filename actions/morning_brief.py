"""
Morning Brief Orchestrator — Triggers the full morning brief experience.

When the wake phrase is detected, this module:
1. Delivers a dramatic Tony Stark-style greeting
2. Speaks a concise summary of Gmail, Calendar, and Fathom
3. Returns a short text summary (not full transcripts)
"""

import random
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from actions.gmail_brief import gmail_brief as _gmail_brief
from actions.calendar_brief import calendar_brief as _calendar_brief
from actions.fathom_brief import fathom_brief as _fathom_brief


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


# Greetings

_GREETINGS = [
    "Good morning, sir. Welcome back. I trust you slept well.",
    "Rise and shine, sir. JARVIS is online and fully operational.",
    "Good morning, sir. All systems nominal. Ready to brief you.",
    "Sir. Good morning. I've been standing by.",
    "Morning, sir. Your brief is ready.",
    "Good morning, sir. The house is secure and the systems are green.",
    "Wakey wakey, sir. Your digital butler is at your service.",
    "Sir. Here's your morning brief.",
]

_TIME_GREETINGS = {
    (5, 7): "Sir. It's early, even for you. Impressive.",
    (7, 10): "Good morning, sir. A civilized hour to awaken.",
    (10, 12): "Sir. It's past ten. I was beginning to worry. Briefly.",
    (12, 14): "Good afternoon, sir. You missed the morning. I saved you a brief.",
    (14, 17): "Sir. Afternoon already. Here's what you missed.",
    (17, 21): "Evening, sir. Not quite a morning brief, but here we are.",
    (21, 24): "Sir. It's late. Briefing you before bed.",
    (0, 5): "Sir. It's the middle of the night. Here's your brief anyway.",
}


def _get_greeting() -> str:
    hour = datetime.now().hour
    for (lo, hi), msg in _TIME_GREETINGS.items():
        if lo <= hour < hi:
            return msg
    return random.choice(_GREETINGS)


def _speak_brief(speak, label, text):
    """Speak a brief section concisely. Truncate to avoid reading walls of text.
    Uses the [PROGRESS] tag so JARVIS announces it directly instead of reacting."""
    if not speak or not text:
        return
    # Keep spoken version short — max ~300 chars per section
    spoken = text.strip()
    if len(spoken) > 300:
        spoken = spoken[:297] + "..."
    try:
        speak(f"[PROGRESS] {label}: {spoken}")
    except Exception:
        pass


def morning_brief(parameters, player=None, session_memory=None, speak=None):
    """Run the full morning brief: greeting + Gmail + Calendar + Fathom.
    Speaks a concise summary. Returns short text (not full transcripts)."""
    greeting = parameters.get("greeting") or _get_greeting()
    email_hours = int(parameters.get("email_hours", 24))
    max_emails = int(parameters.get("max_emails", 15))
    max_events = int(parameters.get("max_events", 20))
    max_recordings = int(parameters.get("max_recordings", 3))  # limited to 3 for testing

    # 1. Bring JARVIS window to foreground (quick, synchronous)
    if player and hasattr(player, 'wake_and_focus'):
        try:
            print("[MorningBrief] Bringing JARVIS to foreground...")
            player.wake_and_focus()
            time.sleep(1.5)
        except Exception as e:
            print(f"[MorningBrief] wake_and_focus failed: {e}")

    # The brief body: fetch each source and speak it as soon as it's ready.
    # Each _speak_brief / progress message is a SEPARATE turn, so JARVIS
    # speaks them one at a time instead of buffering everything to the end.
    def _deliver():
        # Gmail
        gmail_result = _gmail_brief(
            parameters={"hours": email_hours, "max_results": max_emails},
            player=player,
            session_memory=session_memory,
        )
        _speak_brief(speak, "Email", gmail_result)

        # Calendar
        cal_result = _calendar_brief(
            parameters={"max_results": max_events},
            player=player,
            session_memory=session_memory,
        )
        _speak_brief(speak, "Calendar", cal_result)

        # Fathom — fetches, then summarizes in its own background thread
        # with live progress reports.
        _fathom_brief(
            parameters={
                "max_recordings": max_recordings,
                "recent": "true",
                "background": "true",
            },
            player=player,
            session_memory=session_memory,
            speak=speak,
        )

    if speak:
        # Voice mode: return the greeting NOW so JARVIS greets immediately,
        # then deliver Gmail/Calendar/Fathom in the background as they arrive.
        threading.Thread(target=_deliver, daemon=True).start()
        return greeting

    # No-speak (text/manual) mode: run synchronously and return a full summary.
    gmail_result = _gmail_brief(
        parameters={"hours": email_hours, "max_results": max_emails},
        player=player, session_memory=session_memory,
    )
    cal_result = _calendar_brief(
        parameters={"max_results": max_events},
        player=player, session_memory=session_memory,
    )
    fathom_result = _fathom_brief(
        parameters={"max_recordings": max_recordings, "recent": "true"},
        player=player, session_memory=session_memory,
    )
    lines = [
        greeting,
        "",
        "Gmail: " + (gmail_result[:150] if gmail_result else "No important emails."),
        "Calendar: " + (cal_result[:150] if cal_result else "No events."),
        "Fathom: " + (fathom_result[:150] if fathom_result else "No recordings."),
    ]
    return "\n".join(lines)


def morning_greeting(parameters, player=None, session_memory=None):
    """Just deliver a morning greeting (no brief)."""
    greeting = parameters.get("greeting") or _get_greeting()
    if player:
        try:
            player.write_log(f"JARVIS: {greeting}")
        except Exception:
            pass
    return greeting
