"""Rewrite selected bullets to match a job description's wording, via one
LiteLLM call per bullet (REWRITE_MODE=per_bullet, default) or one call for
every selected bullet (REWRITE_MODE=batch). validate.py is the actual
no-fabrication backstop — this module only produces candidate rewrites and
falls back to the original text whenever the model's output can't be trusted
to even parse (malformed JSON, or a bullet id missing from the response).
"""
from __future__ import annotations

import json
import os

from backend.llm import complete_json, load_prompt
from backend.models import Bullet, MasterResume
from backend.schemas import JobRequirements

PROMPT_FILE = "rewrite_bullet.md"


def _rewrite_mode() -> str:
    return os.environ.get("REWRITE_MODE", "per_bullet")


def _master_skills_text(resume: MasterResume) -> str:
    lines = []
    for category, items in resume.skills.items():
        for item in items:
            aliases = f" (aka {', '.join(item.aliases)})" if item.aliases else ""
            lines.append(f"- {item.name}{aliases}")
    return "\n".join(lines)


def _jd_keywords_text(requirements: JobRequirements) -> str:
    seen = dict.fromkeys(requirements.must_have_skills + requirements.nice_to_have_skills + requirements.ats_keywords)
    return ", ".join(seen)


def _build_prompt(bullets: list[Bullet], resume: MasterResume, requirements: JobRequirements) -> str:
    bullets_json = json.dumps(
        [{"id": b.id, "text": b.text, "skills": b.skills} for b in bullets],
        indent=2,
    )
    template = load_prompt(PROMPT_FILE)
    return (
        template.replace("{bullets_json}", bullets_json)
        .replace("{master_skills}", _master_skills_text(resume))
        .replace("{jd_keywords}", _jd_keywords_text(requirements))
    )


def _call_rewrite(bullets: list[Bullet], resume: MasterResume, requirements: JobRequirements) -> dict[str, dict]:
    """Call the LLM once for `bullets`. Returns {bullet_id: {"text", "keywords_used"}}
    for every input id — falling back to the original text for any id that's
    missing from the response, or for every id if the response doesn't parse
    as the expected shape at all.
    """
    fallback = {b.id: {"text": b.text, "keywords_used": []} for b in bullets}

    prompt = _build_prompt(bullets, resume, requirements)
    try:
        data = complete_json(prompt, temperature=0.2)
    except Exception:
        return fallback

    items = data if isinstance(data, list) else data.get("bullets") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return fallback

    result = dict(fallback)
    for item in items:
        if not isinstance(item, dict):
            continue
        bullet_id = item.get("id")
        text = item.get("text")
        if bullet_id in result and isinstance(text, str) and text.strip():
            result[bullet_id] = {"text": text, "keywords_used": item.get("keywords_used") or []}
    return result


def rewrite_bullets(bullets: list[Bullet], resume: MasterResume, requirements: JobRequirements) -> dict[str, dict]:
    """Rewrite every bullet in `bullets` per REWRITE_MODE. Returns
    {bullet_id: {"text": rewritten_or_original, "keywords_used": [...]}} for
    every input id."""
    if not bullets:
        return {}

    if _rewrite_mode() == "batch":
        return _call_rewrite(bullets, resume, requirements)

    results: dict[str, dict] = {}
    for bullet in bullets:
        results.update(_call_rewrite([bullet], resume, requirements))
    return results
