"""
Skills — Claude-Code-style markdown skill system for JARVIS.

A "skill" is a markdown file in skills/ with YAML-ish frontmatter:

    ---
    name: email-triage
    description: When the user wants to sort, prioritize, or reply to emails
    ---

    <full instructions in markdown...>

Progressive disclosure (same idea as Claude Code):
- Only each skill's NAME + DESCRIPTION are injected into the system prompt.
- The full body is loaded on demand when JARVIS calls the load_skill tool.

Drop a new .md file into skills/ and JARVIS gains that capability — no code.
"""

import sys
from pathlib import Path


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def _skills_dir() -> Path:
    d = _base_dir() / "skills"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _parse(text: str):
    """Return (meta dict, body) from a skill markdown file."""
    meta = {"name": "", "description": ""}
    body = text
    if text.lstrip().startswith("---"):
        t = text.lstrip()
        end = t.find("---", 3)
        if end != -1:
            fm = t[3:end]
            body = t[end + 3:].strip()
            for line in fm.strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip().lower()] = v.strip()
    return meta, body


def list_skills() -> list[dict]:
    """All available skills as [{name, description, file}]."""
    skills = []
    for f in sorted(_skills_dir().glob("*.md")):
        try:
            meta, _ = _parse(f.read_text(encoding="utf-8"))
            name = meta.get("name") or f.stem
            skills.append({
                "name": name,
                "description": meta.get("description", ""),
                "file": f.name,
            })
        except Exception:
            continue
    return skills


def load_skill(name: str) -> str | None:
    """Return the full instruction body of a skill by name (fuzzy, case-insensitive)."""
    if not name:
        return None
    target = name.strip().lower()
    files = list(_skills_dir().glob("*.md"))

    # 1. exact frontmatter-name or filename-stem match
    for f in files:
        try:
            meta, body = _parse(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if (meta.get("name", "").lower() == target) or (f.stem.lower() == target):
            return body

    # 2. partial / contains match
    for f in files:
        try:
            meta, body = _parse(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        nm = (meta.get("name", "") or f.stem).lower()
        if target in nm or nm in target or target in f.stem.lower():
            return body

    return None


def skills_prompt_block() -> str:
    """A system-prompt section listing available skills (name + description only)."""
    skills = list_skills()
    if not skills:
        return ""
    lines = [
        "[AVAILABLE SKILLS — reusable playbooks, loaded on demand]",
        "When a user request matches a skill below, FIRST call the load_skill tool "
        "with its name to fetch the full step-by-step instructions, then follow them "
        "(using your other tools as the steps direct). Do not announce that you are "
        "loading a skill — just do it.",
    ]
    for s in skills:
        lines.append(f"- {s['name']}: {s['description']}")
    return "\n".join(lines) + "\n"
