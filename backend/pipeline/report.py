"""Keyword coverage report: which must-haves and nice-to-haves from the JD
actually appear in the tailored resume (final bullet text + skills section),
so the user knows what's covered and what's honestly missing from
master_resume.yaml. The app never adds a missing must-have itself — this
report is what tells the user what to (truthfully) add.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.models import MasterResume
from backend.pipeline.rank import RankedResume
from backend.schemas import JobRequirements


@dataclass
class CoverageReport:
    must_haves_matched: list[str] = field(default_factory=list)
    must_haves_missing: list[str] = field(default_factory=list)
    nice_to_haves_matched: list[str] = field(default_factory=list)


def _alias_index(skills) -> dict[str, str]:
    """surface form (lowercase) -> canonical skill name (lowercase)"""
    index: dict[str, str] = {}
    for items in skills.values():
        for item in items:
            index[item.name.lower()] = item.name.lower()
            for alias in item.aliases:
                index[alias.lower()] = item.name.lower()
    return index


def _forms_by_canonical(skills) -> dict[str, set[str]]:
    """canonical skill name (lowercase) -> every surface form (lowercase)"""
    forms: dict[str, set[str]] = {}
    for items in skills.values():
        for item in items:
            key = item.name.lower()
            forms.setdefault(key, {key})
            forms[key].update(a.lower() for a in item.aliases)
    return forms


def _resume_text(resume: MasterResume, ranked: RankedResume, bullet_text: dict[str, str]) -> str:
    """Everything that will actually appear on the rendered PDF and could
    plausibly carry a keyword match: final bullet text (post-rewrite) plus
    the full skills section. Contact/education are excluded — they aren't
    JD-tailored."""
    parts = []
    for re_ in ranked.experience:
        for rb in re_.bullets:
            parts.append(bullet_text.get(rb.bullet.id, rb.bullet.text))
    for rp in ranked.projects:
        for rb in rp.bullets:
            parts.append(bullet_text.get(rb.bullet.id, rb.bullet.text))
    for items in resume.skills.values():
        for item in items:
            parts.append(item.name)
            parts.extend(item.aliases)
    return "\n".join(parts)


def _contains_term(haystack: str, term: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", haystack, re.IGNORECASE) is not None


def _term_is_covered(term: str, haystack: str, alias_idx: dict[str, str], forms_idx: dict[str, set[str]]) -> bool:
    canonical = alias_idx.get(term.strip().lower())
    candidates = forms_idx.get(canonical, set()) if canonical else {term.strip().lower()}
    return any(_contains_term(haystack, form) for form in candidates)


def build_coverage_report(
    resume: MasterResume,
    ranked: RankedResume,
    requirements: JobRequirements,
    bullet_text: dict[str, str] | None = None,
) -> CoverageReport:
    bullet_text = bullet_text or {}
    haystack = _resume_text(resume, ranked, bullet_text)
    alias_idx = _alias_index(resume.skills)
    forms_idx = _forms_by_canonical(resume.skills)

    must_matched, must_missing = [], []
    for skill in requirements.must_have_skills:
        target = must_matched if _term_is_covered(skill, haystack, alias_idx, forms_idx) else must_missing
        target.append(skill)

    nice_matched = [
        skill for skill in requirements.nice_to_have_skills if _term_is_covered(skill, haystack, alias_idx, forms_idx)
    ]

    return CoverageReport(
        must_haves_matched=must_matched,
        must_haves_missing=must_missing,
        nice_to_haves_matched=nice_matched,
    )
