"""Score and select resume bullets for a job description.

score = 0.6 * cosine_similarity(bullet_embedding, jd_embedding)
      + 0.4 * must_have_keyword_overlap

Selects the top-scoring bullets per experience/project entry within
master_resume.yaml's limits, and the top `limits.max_projects` projects
overall (by each project's best-scoring bullet). No LLM rewriting happens
here — that's rewrite.py (build order step 3); bullet text is untouched.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from backend.llm import embed as default_embed
from backend.models import Bullet, Experience, MasterResume, Project, SkillItem
from backend.schemas import JobRequirements

COSINE_WEIGHT = 0.6
KEYWORD_WEIGHT = 0.4


@dataclass
class RankedBullet:
    bullet: Bullet
    score: float


@dataclass
class RankedExperience:
    experience: Experience
    bullets: list[RankedBullet] = field(default_factory=list)


@dataclass
class RankedProject:
    project: Project
    bullets: list[RankedBullet] = field(default_factory=list)
    score: float = 0.0


@dataclass
class RankedResume:
    experience: list[RankedExperience]
    projects: list[RankedProject]


def _build_alias_index(skills: dict[str, list[SkillItem]]) -> dict[str, str]:
    """Map lowercased alias/name -> canonical skill name, so a JD's wording of
    a skill ("Postgres") matches the master resume's ("PostgreSQL")."""
    index: dict[str, str] = {}
    for items in skills.values():
        for item in items:
            index[item.name.lower()] = item.name
            for alias in item.aliases:
                index[alias.lower()] = item.name
    return index


def _normalize_skill(term: str, alias_index: dict[str, str]) -> str:
    key = term.strip().lower()
    return (alias_index.get(key) or term.strip()).lower()


def _keyword_overlap_score(
    bullet_skills: list[str], must_have_skills: list[str], alias_index: dict[str, str]
) -> float:
    if not must_have_skills:
        return 0.0
    bullet_set = {_normalize_skill(s, alias_index) for s in bullet_skills}
    matched = sum(1 for jd_skill in must_have_skills if _normalize_skill(jd_skill, alias_index) in bullet_set)
    return matched / len(must_have_skills)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def rank_resume(
    resume: MasterResume,
    requirements: JobRequirements,
    jd_text: str,
    embed_fn=default_embed,
) -> RankedResume:
    alias_index = _build_alias_index(resume.skills)

    all_bullets = [b for exp in resume.experience for b in exp.bullets] + [
        b for proj in resume.projects for b in proj.bullets
    ]
    embeddings = embed_fn([jd_text] + [b.text for b in all_bullets])
    jd_embedding, bullet_embeddings = embeddings[0], embeddings[1:]

    scores: dict[str, float] = {}
    for bullet, bullet_embedding in zip(all_bullets, bullet_embeddings):
        cosine = _cosine_similarity(bullet_embedding, jd_embedding)
        keyword = _keyword_overlap_score(bullet.skills, requirements.must_have_skills, alias_index)
        scores[bullet.id] = COSINE_WEIGHT * cosine + KEYWORD_WEIGHT * keyword

    limits = resume.limits

    ranked_experience = []
    for exp in resume.experience:
        top_ids = {b.id for b in sorted(exp.bullets, key=lambda b: scores[b.id], reverse=True)[: limits.experience]}
        selected = [b for b in exp.bullets if b.id in top_ids]  # keep authored order
        ranked_experience.append(
            RankedExperience(experience=exp, bullets=[RankedBullet(b, scores[b.id]) for b in selected])
        )

    ranked_projects_all = []
    for proj in resume.projects:
        top_ids = {b.id for b in sorted(proj.bullets, key=lambda b: scores[b.id], reverse=True)[: limits.projects]}
        selected = [b for b in proj.bullets if b.id in top_ids]
        best_score = max((scores[b.id] for b in proj.bullets), default=0.0)
        ranked_projects_all.append(
            RankedProject(
                project=proj,
                bullets=[RankedBullet(b, scores[b.id]) for b in selected],
                score=best_score,
            )
        )

    top_project_ids = {
        rp.project.id
        for rp in sorted(ranked_projects_all, key=lambda rp: rp.score, reverse=True)[: limits.max_projects]
    }
    ranked_projects = [rp for rp in ranked_projects_all if rp.project.id in top_project_ids]  # keep authored order

    return RankedResume(experience=ranked_experience, projects=ranked_projects)


def drop_lowest_bullet(ranked: RankedResume) -> bool:
    """Remove the single lowest-scoring bullet across the whole ranked resume,
    in place. Returns False if there's nothing left to drop."""
    candidates: list[tuple[float, list[RankedBullet], int]] = []
    for re_ in ranked.experience:
        candidates += [(rb.score, re_.bullets, i) for i, rb in enumerate(re_.bullets)]
    for rp in ranked.projects:
        candidates += [(rb.score, rp.bullets, i) for i, rb in enumerate(rp.bullets)]

    if not candidates:
        return False

    _, bullet_list, index = min(candidates, key=lambda c: c[0])
    del bullet_list[index]
    return True
