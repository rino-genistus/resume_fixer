"""The no-fabrication backstop (CLAUDE.md non-negotiable #1): reject a
rewrite — falling back to the bullet's original text — if it adds a number
not in the source, adds a skill/JD keyword not authorized for it (the
bullet's own skills, or the master skills list; aliases count), or blows the
230-character budget. Every rejection carries its reason for report.json.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from backend.models import Bullet, MasterResume, SkillItem
from backend.schemas import JobRequirements

MAX_LENGTH = 230

_NUMBER_RE = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?%?\+?")


@dataclass
class ValidationResult:
    bullet_id: str
    text: str  # what to actually render: the rewrite if accepted, else the original
    original_text: str
    accepted: bool
    reason: str | None = None


def _numbers(text: str) -> set[str]:
    return set(_NUMBER_RE.findall(text))


def _build_alias_index(skills: dict[str, list[SkillItem]]) -> dict[str, str]:
    index: dict[str, str] = {}
    for items in skills.values():
        for item in items:
            index[item.name.lower()] = item.name
            for alias in item.aliases:
                index[alias.lower()] = item.name
    return index


def _canonical(term: str, alias_index: dict[str, str]) -> str:
    return (alias_index.get(term.strip().lower()) or term.strip()).lower()


def _contains_term(text: str, term: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text, re.IGNORECASE) is not None


def _added_unauthorized_keyword(
    original_text: str,
    rewritten_text: str,
    bullet_skills: list[str],
    resume: MasterResume,
    requirements: JobRequirements,
    alias_index: dict[str, str],
) -> str | None:
    """Scan for the recognizable skill/keyword vocabulary (JD keywords + the
    master skills list — the only terms we can reliably recognize as "a skill")
    and flag the first one that's newly present in the rewrite but isn't
    authorized for this bullet."""
    vocabulary: set[str] = set(
        requirements.must_have_skills + requirements.nice_to_have_skills + requirements.ats_keywords
    )
    authorized = {_canonical(s, alias_index) for s in bullet_skills}
    for items in resume.skills.values():
        for item in items:
            vocabulary.add(item.name)
            vocabulary.update(item.aliases)
            authorized.add(item.name.lower())

    for term in sorted((t for t in vocabulary if t.strip()), key=len, reverse=True):
        if _contains_term(rewritten_text, term) and not _contains_term(original_text, term):
            if _canonical(term, alias_index) not in authorized:
                return term
    return None


def validate_rewrite(
    bullet: Bullet,
    rewritten_text: str,
    resume: MasterResume,
    requirements: JobRequirements,
) -> ValidationResult:
    if rewritten_text.strip() == bullet.text.strip():
        return ValidationResult(bullet.id, bullet.text, bullet.text, accepted=True)

    if len(rewritten_text) > MAX_LENGTH:
        return ValidationResult(
            bullet.id,
            bullet.text,
            bullet.text,
            accepted=False,
            reason=f"rewrite is {len(rewritten_text)} chars, exceeds the {MAX_LENGTH}-char limit",
        )

    added_numbers = _numbers(rewritten_text) - _numbers(bullet.text)
    if added_numbers:
        return ValidationResult(
            bullet.id,
            bullet.text,
            bullet.text,
            accepted=False,
            reason=f"added number(s) not in source: {', '.join(sorted(added_numbers))}",
        )

    alias_index = _build_alias_index(resume.skills)
    unauthorized = _added_unauthorized_keyword(
        bullet.text, rewritten_text, bullet.skills, resume, requirements, alias_index
    )
    if unauthorized:
        return ValidationResult(
            bullet.id,
            bullet.text,
            bullet.text,
            accepted=False,
            reason=f"added unauthorized skill/keyword: {unauthorized!r}",
        )

    return ValidationResult(bullet.id, rewritten_text, bullet.text, accepted=True)
