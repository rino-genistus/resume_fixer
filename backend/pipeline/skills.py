"""Reorder skill categories/items so JD matches surface first. Pure
presentation, no LLM — and since this only reorders resume.skills (the
master list), it never introduces a skill that isn't already there.
"""
from __future__ import annotations

from backend.models import MasterResume, SkillItem
from backend.schemas import JobRequirements


def _jd_term_set(requirements: JobRequirements) -> set[str]:
    terms = requirements.must_have_skills + requirements.nice_to_have_skills + requirements.ats_keywords
    return {t.strip().lower() for t in terms if t.strip()}


def _skill_matches_jd(item: SkillItem, jd_terms: set[str]) -> bool:
    forms = {item.name.lower(), *(a.lower() for a in item.aliases)}
    return bool(forms & jd_terms)


def reorder_skills(resume: MasterResume, requirements: JobRequirements) -> dict[str, list[SkillItem]]:
    """JD-matching items first within each category; JD-matching categories
    (by match count) before non-matching ones. Ties keep master_resume.yaml's
    original order. Category/item membership is unchanged — only order.
    """
    jd_terms = _jd_term_set(requirements)

    entries = []
    for category, items in resume.skills.items():
        matched = [i for i in items if _skill_matches_jd(i, jd_terms)]
        unmatched = [i for i in items if not _skill_matches_jd(i, jd_terms)]
        entries.append((category, matched + unmatched, len(matched)))

    entries.sort(key=lambda e: e[2], reverse=True)
    return {category: items for category, items, _match_count in entries}
