"""
Self-improvement loop for JARVIS (Hermes-style).

Periodically, a lightweight background "review" reads the recent conversation
and decides — autonomously — whether to:
  - save a durable fact about the user to long-term memory, and/or
  - codify a repeatable workflow into a reusable skill.

This mirrors Hermes Agent's counter-triggered review fork: every N user turns
we run a memory review, every N tool iterations we run a skill review. The
reviews run on a Gemini text model (not the Live session) so they never block
the conversation, and they fail silently (e.g. if quota is exhausted).
"""

import json
import sys
from pathlib import Path


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def _gemini_key() -> str | None:
    try:
        cfg = json.loads((_base_dir() / "config" / "api_keys.json").read_text(encoding="utf-8"))
        return cfg.get("gemini_api_key")
    except Exception:
        return None


_MODELS = ["gemini-flash-latest", "gemini-2.5-flash", "gemini-2.0-flash"]


def _gemini_json(prompt: str) -> dict | None:
    """Run a one-shot text generation and parse a JSON object from the reply.
    Fails fast on quota; returns None on any failure."""
    key = _gemini_key()
    if not key:
        return None
    try:
        from google import genai
    except Exception:
        return None

    import time as _time
    client = genai.Client(api_key=key)
    last_err = None
    for model in _MODELS:
        for attempt in range(2):
            try:
                resp = client.models.generate_content(model=model, contents=prompt)
                text = (resp.text or "").strip()
                if text.startswith("```"):
                    text = text.split("```", 2)[1]
                    if text.startswith("json"):
                        text = text[4:]
                    text = text.strip()
                return json.loads(text)
            except Exception as e:
                last_err = e
                msg = str(e).lower()
                if "resource_exhausted" in msg or "quota" in msg or "limit: 0" in msg:
                    return None  # quota — don't bother retrying other models
                if ("503" in msg or "unavailable" in msg) and attempt == 0:
                    _time.sleep(1)
                    continue
                break
    print(f"[SelfImprove] review failed: {str(last_err)[:120]}")
    return None


def review_memory(transcript: str, known: str = "") -> list[dict]:
    """Decide if anything in the recent conversation is worth saving to memory.
    Returns a list of {category, key, value}."""
    prompt = (
        "You review a recent conversation between a user and their assistant JARVIS, "
        "and extract NEW, durable facts about the USER worth remembering long-term: "
        "name, age, location, job, preferences, hobbies, active projects, relationships, "
        "future plans, habits. Ignore one-off tasks, questions, and transient details. "
        "Do NOT repeat facts already known (listed below).\n\n"
        f"ALREADY KNOWN:\n{known or '(nothing yet)'}\n\n"
        "Respond ONLY with JSON:\n"
        '{"memories": [{"category": "identity|preferences|projects|relationships|wishes|notes", '
        '"key": "snake_case_key", "value": "concise value in English"}]}\n'
        "Use an empty list if there is nothing genuinely new and durable.\n\n"
        f"CONVERSATION:\n{transcript}"
    )
    data = _gemini_json(prompt)
    if not data:
        return []
    out = []
    for m in (data.get("memories") or []):
        if isinstance(m, dict) and m.get("key") and m.get("value"):
            out.append({
                "category": m.get("category", "notes"),
                "key": m["key"],
                "value": m["value"],
            })
    return out


def review_skill(transcript: str, existing_names: list[str]) -> dict | None:
    """Decide if a reusable skill should be created from the recent conversation.
    Returns {name, description, body} or None."""
    prompt = (
        "You review a recent conversation where the assistant JARVIS performed a task "
        "using tools. If a GENUINELY REUSABLE, multi-step workflow emerged that would help "
        "JARVIS handle this kind of request again, codify it as a skill. Only do this for a "
        "repeatable procedure — NOT a one-off, trivial, or single-tool action. Do NOT "
        "recreate a skill that already exists (existing skills listed below).\n\n"
        f"EXISTING SKILLS: {', '.join(existing_names) or '(none)'}\n\n"
        "Respond ONLY with JSON:\n"
        '{"skill": {"name": "kebab-case-name", "description": "When the user wants to ...", '
        '"body": "# Title\\n\\nNumbered step-by-step markdown, which tools to use, tips."}}\n'
        'or {"skill": null} if nothing is worth saving.\n\n'
        f"CONVERSATION:\n{transcript}"
    )
    data = _gemini_json(prompt)
    if not data:
        return None
    skill = data.get("skill")
    if isinstance(skill, dict) and skill.get("name") and skill.get("body"):
        return {
            "name": skill["name"],
            "description": skill.get("description", ""),
            "body": skill["body"],
        }
    return None
