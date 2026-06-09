"""
Fathom Brief — Fetches meeting transcripts from Fathom.ai and creates
organized todo lists and a searchable knowledge base.

Instead of reading transcripts aloud, this module:
1. Fetches today's recordings from Fathom API
2. Creates organized todo/action item files
3. Stores transcripts in a knowledge base for later querying
4. Returns a brief spoken summary (not full transcripts)

API: https://developers.fathom.ai/
Auth: X-Api-Key header
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _config_path() -> Path:
    return _base_dir() / "config" / "api_keys.json"


def _knowledge_base_dir() -> Path:
    d = _base_dir() / "knowledge_base" / "fathom"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _todos_dir() -> Path:
    d = _base_dir() / "knowledge_base" / "todos"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _get_api_key() -> str | None:
    try:
        cfg = json.loads(_config_path().read_text(encoding="utf-8"))
        return cfg.get("fathom_api_key")
    except Exception:
        return None


def _get_gemini_key() -> str | None:
    try:
        cfg = json.loads(_config_path().read_text(encoding="utf-8"))
        return cfg.get("gemini_api_key")
    except Exception:
        return None


# Model used for summarizing transcripts (text generation, not Live audio)
_SUMMARY_MODEL = "gemini-2.5-flash"


def _summarize_with_gemini(title: str, transcript_text: str) -> dict | None:
    """Use the Gemini API to summarize a transcript and extract action items.

    Returns {"summary": str, "action_items": [str, ...]} or None on failure.
    """
    if not transcript_text.strip():
        return None

    gemini_key = _get_gemini_key()
    if not gemini_key:
        print("[FathomBrief] No Gemini API key — skipping AI summary.")
        return None

    # Cap transcript length to stay within token limits
    # (gemini-2.5-flash handles ~1M tokens; 200k chars is a safe, generous cap)
    transcript_text = transcript_text[:200000]

    prompt = (
        f"You are an expert chief-of-staff analyzing a meeting transcript titled '{title}'.\n\n"
        "Read the ENTIRE transcript carefully and produce a thorough analysis. Do not just "
        "capture explicit commitments — also infer the broader scope of work and strategic "
        "expectations that the participant is implicitly responsible for delivering.\n\n"
        "Produce:\n\n"
        "1. summary: A clear 3-5 sentence summary of what the meeting was about, including "
        "the context and the most important outcomes.\n\n"
        "2. immediate_actions: Concrete next steps that were EXPLICITLY agreed upon or "
        "committed to in the meeting. Be specific and note the owner if mentioned "
        "(e.g. 'Bryan to send WISE payment details'). These are the clear, near-term tasks.\n\n"
        "3. responsibilities: The broader scope of work, strategic deliverables, and implied "
        "responsibilities that came out of the discussion — the things the participant was "
        "actually hired/expected to do, even if not stated as a discrete task. Include "
        "specific tools, systems, processes, or goals mentioned (e.g. 'Audit automation "
        "opportunities across GoHighLevel, ClickUp, and Slack'). Capture technical "
        "requirements, workflows, and expectations discussed at length. If the meeting was "
        "purely operational with no broader scope, return an empty list.\n\n"
        "Be comprehensive — it is better to capture an implied responsibility than to miss it. "
        "Each item should be a specific, actionable string.\n\n"
        "Respond ONLY with valid JSON in this exact format:\n"
        '{"summary": "...", "immediate_actions": ["task 1", ...], "responsibilities": ["item 1", ...]}\n\n'
        "TRANSCRIPT:\n"
        f"{transcript_text}"
    )

    import time as _time
    try:
        from google import genai
    except Exception as e:
        print(f"[FathomBrief] google.genai not available: {e}")
        return None

    client = genai.Client(api_key=gemini_key)

    # Try each model, falling back on failure. Distinguish error types:
    #  - quota exhausted (429 + "limit: 0"/"quota"/"RESOURCE_EXHAUSTED"):
    #    a hard cap that won't recover by retrying — skip straight to next
    #    model, and give up fast (don't waste minutes).
    #  - transient overload (503/UNAVAILABLE): short retry.
    models = ["gemini-flash-latest", _SUMMARY_MODEL, "gemini-2.0-flash"]
    last_err = None
    quota_hit = False
    for model in models:
        for attempt in range(2):  # max 2 attempts per model
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                )
                text = (response.text or "").strip()

                # Strip markdown code fences if present
                if text.startswith("```"):
                    text = text.split("```", 2)[1]
                    if text.startswith("json"):
                        text = text[4:]
                    text = text.strip()

                data = json.loads(text)
                return {
                    "summary": data.get("summary", ""),
                    "immediate_actions": data.get("immediate_actions", []),
                    "responsibilities": data.get("responsibilities", []),
                }
            except Exception as e:
                last_err = e
                msg = str(e).lower()
                is_quota = (
                    "resource_exhausted" in msg
                    or "quota" in msg
                    or "limit: 0" in msg
                    or ("429" in msg and "retry" not in msg)
                )
                is_overload = "503" in msg or "unavailable" in msg or "overloaded" in msg

                if is_quota:
                    # Hard quota cap — retrying won't help. Move to next model now.
                    print(f"[FathomBrief] {model} quota exhausted — skipping.")
                    break
                elif is_overload and attempt == 0:
                    print(f"[FathomBrief] {model} overloaded, one quick retry...")
                    _time.sleep(2)
                    continue
                else:
                    print(f"[FathomBrief] {model} error: {str(e)[:120]}")
                    break  # try next model

    if "resource_exhausted" in str(last_err).lower() or "quota" in str(last_err).lower():
        print("[FathomBrief] All models quota-exhausted — Gemini free tier limit reached.")
    else:
        print(f"[FathomBrief] Gemini summary failed: {str(last_err)[:150]}")
    return None


def _api_request(url: str, api_key: str, retries: int = 3) -> dict:
    """GET the Fathom API with retries — the API is flaky (timeouts, 500s, 502s)."""
    import time as _time
    headers = {
        "X-Api-Key": api_key,
        "Accept": "application/json",
    }
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=45) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                wait = 3 * (attempt + 1)
                print(f"[FathomBrief] Fetch attempt {attempt + 1}/{retries} failed "
                      f"({str(e)[:60]}); retrying in {wait}s...")
                _time.sleep(wait)
    raise last_err


def _get_recordings(api_key: str, created_after: str = None, created_before: str = None, limit: int = 5) -> list:
    """Fetch recordings from Fathom API with optional date filters.
    Uses small page sizes to avoid API timeouts/502s."""
    url = "https://api.fathom.ai/external/v1/meetings?include_transcript=true&include_summary=true&calendar_invitees_domains_type=all"
    if created_after:
        url += f"&created_after={created_after}"
    if created_before:
        url += f"&created_before={created_before}"

    all_items = []
    page = 0
    max_pages = 3  # safety limit
    while url and page < max_pages:
        page += 1
        try:
            response = _api_request(url, api_key)
        except Exception as e:
            print(f"[FathomBrief] API error on page {page}: {e}")
            break
        items = response.get("items", response.get("results", []))
        all_items.extend(items)
        next_cursor = response.get("next_cursor")
        # Build next page URL preserving all params
        if next_cursor and len(all_items) < limit:
            url = f"https://api.fathom.ai/external/v1/meetings?include_transcript=true&include_summary=true&calendar_invitees_domains_type=all&cursor={next_cursor}"
        else:
            url = None
    return all_items


def _save_to_knowledge_base(recording: dict):
    """Save a recording's transcript and metadata to the knowledge base."""
    rec_id = recording.get("id", "unknown")
    title = recording.get("title", "Untitled meeting")
    created = recording.get("created_at", datetime.now().isoformat())

    # Create a safe filename
    safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)
    date_str = created[:10] if created else "unknown"
    filename = f"{date_str}_{safe_title}_{rec_id}.json"
    filepath = _knowledge_base_dir() / filename

    # Store the full recording data
    kb_entry = {
        "id": rec_id,
        "title": title,
        "created_at": created,
        "duration": recording.get("duration", 0),
        "summary": recording.get("summary", ""),
        "transcript": recording.get("transcript", []),
        "action_items": recording.get("action_items", []),
        "saved_at": datetime.now().isoformat(),
    }

    filepath.write_text(json.dumps(kb_entry, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[FathomBrief] Saved to KB: {filename}")
    return filepath


def _format_transcript_text(transcript: list) -> str:
    """Format transcript entries into readable text for AI analysis."""
    lines = []
    for entry in transcript:
        speaker = entry.get("speaker", {}).get("display_name", "Unknown")
        text = entry.get("text", "")
        ts = entry.get("timestamp", "")
        lines.append(f"[{ts}] {speaker}: {text}")
    return "\n".join(lines)


def _todo_filepath(recording: dict) -> Path:
    """Compute the todo markdown path for a recording."""
    title = recording.get("title", "Untitled meeting")
    rec_id = recording.get("id", "unknown")
    created = recording.get("created_at", "")
    date_str = created[:10] if created else datetime.now().strftime("%Y-%m-%d")
    safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title).strip()
    return _todos_dir() / f"fathom_todo_{date_str}_{safe_title}_{rec_id}.md"


def _write_todo_markdown(recording: dict, summary: str, immediate_actions: list,
                         responsibilities: list, pending: bool = False) -> Path:
    """Write the todo markdown file. If pending=True, marks the summary as
    still being generated (placeholder)."""
    title = recording.get("title", "Untitled meeting")
    rec_id = recording.get("id", "unknown")
    created = recording.get("created_at", "")
    date_str = created[:10] if created else datetime.now().strftime("%Y-%m-%d")
    filepath = _todo_filepath(recording)

    lines = [
        f"# {title}",
        f"Date: {date_str}",
        f"Meeting ID: {rec_id}",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    lines.append("## Summary")
    lines.append("")
    if summary:
        lines.append(summary)
    elif pending:
        lines.append("*Summary is being generated...*")
    else:
        lines.append("*Summary unavailable — AI quota may be exhausted. "
                     "Run fathom_analyze on this meeting later to generate it.*")
    lines.append("")

    lines.append("## Immediate Actions")
    lines.append("")
    if immediate_actions:
        for t in immediate_actions:
            lines.append(f"- [ ] {t}")
    elif pending:
        lines.append("*Pending...*")
    else:
        lines.append("*No explicit action items identified (or AI unavailable).*")
    lines.append("")

    if responsibilities:
        lines.append("## Initial Responsibilities & Scope")
        lines.append("")
        for r in responsibilities:
            lines.append(f"- [ ] {r}")
        lines.append("")

    filepath.write_text("\n".join(lines), encoding="utf-8")
    return filepath


def _create_todo_file(recording: dict):
    """Create an individual todo/action item file for a single recording.

    Writes a placeholder file IMMEDIATELY so a todo always exists, then
    upgrades it with an AI summary + action items once Gemini responds.
    Resilient: if Gemini fails (e.g. quota), the file remains with a clear
    note instead of being lost.

    Returns (filepath, ai_succeeded: bool).
    """
    title = recording.get("title", "Untitled meeting")
    native_action_items = recording.get("action_items") or []
    summary = recording.get("summary", "") or ""
    transcript = recording.get("transcript") or []

    # Fold any native Fathom action items into immediate actions up front
    native_actions = []
    for item in native_action_items:
        text = item.get("text", "")
        assignee = item.get("assignee", "")
        due = item.get("due_date", "")
        suffix = ""
        if assignee and assignee != "Unassigned":
            suffix += f" (@{assignee})"
        if due:
            suffix += f" [due: {due}]"
        if text:
            native_actions.append(f"{text}{suffix}")

    # 1. Write a placeholder file immediately so there's always a todo.
    filepath = _write_todo_markdown(
        recording, summary, list(native_actions), [], pending=True
    )

    # 2. If we already have everything from Fathom, finalize now.
    if summary and native_action_items:
        _write_todo_markdown(recording, summary, native_actions, [], pending=False)
        print(f"[FathomBrief] Todo file created: {filepath.name}")
        return filepath, True

    # 3. Otherwise, summarize the transcript with Gemini.
    transcript_text = _format_transcript_text(transcript)
    ai = None
    if transcript_text.strip():
        print(f"[FathomBrief] Summarizing '{title}' with Gemini...")
        ai = _summarize_with_gemini(title, transcript_text)

    immediate_actions = list(native_actions)
    responsibilities = []
    if ai:
        if not summary:
            summary = ai.get("summary", "")
        immediate_actions = ai.get("immediate_actions", []) + native_actions
        responsibilities = ai.get("responsibilities", [])

    # 4. Final write (real content, or a clear "unavailable" note if AI failed).
    _write_todo_markdown(recording, summary, immediate_actions, responsibilities, pending=False)
    ai_ok = ai is not None
    status = "with AI summary" if ai_ok else "WITHOUT summary (AI unavailable)"
    print(f"[FathomBrief] Todo file created {status}: {filepath.name}")
    return filepath, ai_ok


def fathom_analyze(parameters: dict, player=None, session_memory=None) -> str:
    """Analyze a specific Fathom meeting transcript with AI to extract
    a smart summary and actionable todos.

    Parameters:
        meeting_id (str): The Fathom meeting/recording ID.
        title (str): Meeting title (optional, for display).
        transcript_text (str): The full transcript text to analyze.
        or
        kb_file (str): Path to a KB JSON file to load and analyze.
    """
    transcript_text = parameters.get("transcript_text", "").strip()
    kb_file = parameters.get("kb_file", "").strip()
    meeting_id = parameters.get("meeting_id", "unknown")
    title = parameters.get("title", "Meeting")

    # If kb_file provided, load transcript from there
    if kb_file and not transcript_text:
        kb_path = _knowledge_base_dir() / kb_file
        if not kb_path.exists():
            # Try as absolute/relative path
            kb_path = Path(kb_file)
        if kb_path.exists():
            try:
                data = json.loads(kb_path.read_text(encoding="utf-8"))
                transcript = data.get("transcript", [])
                transcript_text = _format_transcript_text(transcript)
                title = data.get("title", title)
                meeting_id = data.get("id", meeting_id)
            except Exception as e:
                return f"Error reading KB file: {e}"

    if not transcript_text:
        # List available KB files for the user
        kb_files = sorted(_knowledge_base_dir().glob("*.json"), reverse=True)
        if not kb_files:
            return "No meeting transcripts found in the knowledge base, sir."

        parts = ["Available meeting transcripts to analyze:"]
        for f in kb_files[:10]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                t = data.get("title", "Untitled")
                d = data.get("created_at", "")[:10]
                parts.append(f"  • {t} ({d}) — kb_file: {f.name}")
            except Exception:
                parts.append(f"  • {f.name}")
        parts.append("\nSay 'analyze the meeting about X' and I'll process it.")
        return "\n".join(parts)

    # The actual AI analysis happens in Gemini — this function returns
    # the transcript data so Gemini can analyze it and call back with
    # the structured results
    return json.dumps({
        "status": "ready_for_analysis",
        "title": title,
        "meeting_id": meeting_id,
        "transcript_length": len(transcript_text),
        "transcript_text": transcript_text[:8000],  # Cap for token limits
        "message": f"Transcript for '{title}' ready. Gemini should analyze and call fathom_save_todo.",
    })


def fathom_save_todo(parameters: dict, player=None, session_memory=None) -> str:
    """Save an AI-generated analysis as a todo file. Called by Gemini
    after analyzing a transcript via fathom_analyze.

    Parameters:
        title (str): Meeting title.
        meeting_id (str): Fathom recording ID.
        date (str): Meeting date YYYY-MM-DD.
        summary (str): AI-generated summary.
        action_items (str): AI-generated action items as markdown.
    """
    title = parameters.get("title", "Meeting")
    meeting_id = parameters.get("meeting_id", "unknown")
    date_str = parameters.get("date", datetime.now().strftime("%Y-%m-%d"))
    summary = parameters.get("summary", "")
    action_items = parameters.get("action_items", "")

    if not summary and not action_items:
        return "No content to save, sir."

    # Build a safe filename
    safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title).strip()
    filename = f"fathom_todo_{date_str}_{safe_title}_{meeting_id}.md"
    filepath = _todos_dir() / filename

    lines = [
        f"# {title}",
        f"Date: {date_str}",
        f"Meeting ID: {meeting_id}",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    lines.append("## Summary")
    lines.append("")
    lines.append(summary or "*No summary provided.*")
    lines.append("")

    lines.append("## Action Items")
    lines.append("")
    if action_items:
        lines.append(action_items)
    else:
        lines.append("*No action items identified.*")
    lines.append("")

    filepath.write_text("\n".join(lines), encoding="utf-8")
    print(f"[FathomBrief] AI todo file created: {filename}")
    return f"Todo file saved: {filename}"


def _search_knowledge_base(query: str) -> list:
    """Search the knowledge base for relevant meeting transcripts."""
    results = []
    query_lower = query.lower()

    for f in _knowledge_base_dir().glob("*.json"):
        try:
            entry = json.loads(f.read_text(encoding="utf-8"))
            score = 0
            # Match against title
            title = entry.get("title", "").lower()
            if query_lower in title:
                score += 10
            # Match against summary
            summary = entry.get("summary", "").lower()
            if query_lower in summary:
                score += 5
            # Match against transcript content
            transcript = entry.get("transcript", [])
            for t in transcript:
                text = t.get("text", "").lower()
                if query_lower in text:
                    score += 2
            # Match against action items
            for ai in entry.get("action_items") or []:
                if query_lower in ai.get("text", "").lower():
                    score += 3

            if score > 0:
                results.append({
                    "score": score,
                    "title": entry.get("title", "Untitled"),
                    "date": entry.get("created_at", "")[:10],
                    "summary": entry.get("summary", "")[:200],
                    "action_items": entry.get("action_items", []),
                    "file": str(f.name),
                })
        except Exception:
            continue

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def _find_latest_todo_file(date_str: str = None) -> Path | None:
    """Find the most recent Fathom todo file."""
    if date_str:
        path = _todos_dir() / f"fathom_todos_{date_str}.md"
        if path.exists():
            return path
    # Find most recent
    files = sorted(_todos_dir().glob("fathom_todo_*.md"), reverse=True)
    return files[0] if files else None


def _process_recordings(recordings: list, speak=None, player=None):
    """Save each recording to the KB and build its AI todo file.
    Reports progress before/after each meeting via voice (`speak`) and the
    UI log (`player.write_log`). Returns (todo_files, total_items, failures).
    """
    todo_files = []
    total_items = 0
    failures = 0
    count = len(recordings)

    def _report(voice_msg, log_msg=None):
        if player:
            try:
                player.write_log(log_msg or voice_msg)
            except Exception:
                pass
        if speak:
            try:
                # [PROGRESS] tag tells JARVIS to read the line aloud verbatim
                # as a status update, NOT to react/respond to it (see prompt.txt).
                speak(f"[PROGRESS] {voice_msg}")
            except Exception:
                pass

    for idx, rec in enumerate(recordings, 1):
        title = rec.get("title", "Untitled")

        # Announce BEFORE starting (so the user knows what's happening)
        _report(
            f"I'm now working on meeting {idx} of {count}: the {title} call.",
            f"[Fathom] ({idx}/{count}) Summarizing: {title}",
        )

        try:
            _save_to_knowledge_base(rec)
        except Exception as e:
            print(f"[FathomBrief] KB save error: {e}")

        ai_ok = False
        try:
            todo_path, ai_ok = _create_todo_file(rec)
            if todo_path:
                todo_files.append(todo_path)
        except Exception as e:
            print(f"[FathomBrief] Todo file error: {e}")
        total_items += len(rec.get("action_items") or [])

        # Announce AFTER, noting whether the AI summary succeeded
        if ai_ok:
            _report(
                f"Meeting {idx} of {count} is done. I've saved the summary and to-do list for {title}.",
                f"[Fathom] ({idx}/{count}) ✓ Done: {title}",
            )
        else:
            failures += 1
            _report(
                f"Meeting {idx} of {count}, {title}, is saved, but I couldn't summarize it — "
                f"the AI quota is used up. I'll finish it once the quota resets.",
                f"[Fathom] ({idx}/{count}) ⚠ Saved without summary (AI unavailable): {title}",
            )

    # Final wrap-up
    if failures == 0:
        _report(
            f"All done, sir. I've created {len(todo_files)} to-do "
            f"list{'s' if len(todo_files) != 1 else ''} from your meetings.",
            f"[Fathom] Complete — {len(todo_files)} to-do list(s) created.",
        )
    else:
        _report(
            f"All done, sir. {len(todo_files) - failures} of {count} were fully summarized, "
            f"and {failures} are saved but still need a summary, since the AI quota is used up. "
            f"I'll finish those once it resets.",
            f"[Fathom] Complete — {failures}/{count} pending summary (AI quota exhausted).",
        )

    return todo_files, total_items, failures


def fathom_brief(parameters: dict, player=None, session_memory=None, speak=None) -> str:
    """Fetch Fathom recordings and create organized files.

    Does NOT read transcripts aloud. Instead:
    - Saves transcripts to knowledge base
    - Creates a todo/action item markdown file (AI-summarized)
    - Returns a brief spoken summary

    Parameters:
        max_recordings (int): Max recordings to process (default 10).
        recent (bool): If True, ignore date filter and fetch most recent N recordings.
        background (bool): If True (and speak provided), summarize meetings in a
                           background thread and report progress as each completes.
    """
    api_key = _get_api_key()
    if not api_key:
        return "Fathom API key not configured, sir."

    max_recordings = int(parameters.get("max_recordings", 10))
    recent_mode = str(parameters.get("recent", "")).lower() in ("true", "1", "yes")
    # Default to background mode whenever we have a voice channel, so JARVIS
    # stays responsive and can keep talking while summaries are generated.
    _bg_default = "true" if speak else ""
    background = str(parameters.get("background", _bg_default)).lower() in ("true", "1", "yes")

    # Get today's date range in UTC (unless recent mode)
    now = datetime.now(timezone.utc)
    if recent_mode:
        created_after = None
        created_before = None
        print(f"[FathomBrief] Fetching {max_recordings} most recent recordings...")
    else:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=23, minute=59, second=59, microsecond=0)
        created_after = start.isoformat().replace("+00:00", "Z")
        created_before = end.isoformat().replace("+00:00", "Z")
        print(f"[FathomBrief] Fetching today's recordings...")

    recordings = _get_recordings(api_key, created_after, created_before)
    recordings = recordings[:max_recordings]

    if not recordings:
        if recent_mode:
            return "No Fathom recordings found, sir."
        return "No Fathom recordings today, sir."

    count = len(recordings)
    titles = [r.get("title", "Untitled") for r in recordings]

    # Background mode: announce first, then process + report progress in a thread.
    if background and (speak or player):
        import threading

        def _worker():
            _process_recordings(recordings, speak=speak, player=player)

        threading.Thread(target=_worker, daemon=True).start()

        parts = [
            f"Found {count} meeting{'s' if count != 1 else ''}{' today' if not recent_mode else ''}.",
        ]
        for t in titles[:5]:
            parts.append(f"  {t}")
        if count > 5:
            parts.append(f"  and {count - 5} more")
        parts.append(
            "I'm creating the summaries and to-do lists now. "
            "I'll keep you posted on each one."
        )
        return "\n".join(parts)

    # Synchronous mode (default): process everything before returning.
    todo_files, total_items, _failures = _process_recordings(recordings, speak=None, player=player)

    parts = [
        f"Found {count} meeting{'s' if count != 1 else ''}{' today' if not recent_mode else ''}.",
    ]
    for t in titles[:5]:
        parts.append(f"  {t}")
    if count > 5:
        parts.append(f"  and {count - 5} more")

    if total_items > 0:
        parts.append(f"Extracted {total_items} action items.")

    if todo_files:
        parts.append(f"Created {len(todo_files)} todo file{'s' if len(todo_files) != 1 else ''}.")
    parts.append("All transcripts saved to the knowledge base.")

    return "\n".join(parts)


def fathom_search(parameters: dict, player=None, session_memory=None) -> str:
    """Search the Fathom knowledge base for relevant meetings.

    Parameters:
        query (str): Search query — topics, names, keywords.
    """
    query = parameters.get("query", "").strip()
    if not query:
        return "Sir, what would you like me to search for in your meeting recordings?"

    results = _search_knowledge_base(query)

    if not results:
        return f"No meetings found matching '{query}', sir."

    parts = [f"Found {len(results)} relevant meeting{'s' if len(results) != 1 else ''} for '{query}':"]
    for r in results[:5]:
        lines = [
            f"  [Recording] {r['title']} ({r['date']})",
        ]
        if r["summary"]:
            lines.append(f"     Summary: {r['summary'][:150]}")
        if r["action_items"]:
            lines.append(f"     Action items:")
            for ai in r["action_items"][:3]:
                lines.append(f"       • {ai.get('text', '')}")
        parts.extend(lines)

    return "\n".join(parts)


def fathom_todos(parameters: dict, player=None, session_memory=None) -> str:
    """Read back the latest Fathom todo list.

    Parameters:
        date (str): Optional date YYYY-MM-DD. Defaults to latest.
    """
    date_str = parameters.get("date", None)
    todo_path = _find_latest_todo_file(date_str)

    if not todo_path or not todo_path.exists():
        if date_str:
            return f"No todo list found for {date_str}, sir."
        return "No Fathom todo lists found, sir."

    content = todo_path.read_text(encoding="utf-8")
    # Return the markdown content — concise enough to speak key items
    lines = [l for l in content.split("\n") if l.startswith("- [ ]")]
    if not lines:
        return f"Todo list exists at {todo_path.name} but has no action items."

    parts = [f"Fathom action items from {todo_path.stem}:"]
    for line in lines[:10]:
        task = line.replace("- [ ] ", "").strip()
        parts.append(f"  • {task}")
    if len(lines) > 10:
        parts.append(f"  ...and {len(lines) - 10} more items")

    return "\n".join(parts)


if __name__ == "__main__":
    print(fathom_brief({}))
