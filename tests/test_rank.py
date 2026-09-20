from backend.models import Bullet, Experience, Limits, MasterResume, Project, SkillItem, Contact
from backend.pipeline.rank import (
    RankedBullet,
    RankedExperience,
    RankedProject,
    RankedResume,
    _build_alias_index,
    _cosine_similarity,
    _keyword_overlap_score,
    drop_lowest_bullet,
    rank_resume,
)
from backend.schemas import JobRequirements


def _skills():
    return {
        "Languages": [SkillItem(name="Python"), SkillItem(name="PostgreSQL", aliases=["Postgres"])],
    }


def test_cosine_similarity_identical_vectors_is_one():
    assert _cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_cosine_similarity_orthogonal_vectors_is_zero():
    assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_similarity_zero_vector_is_zero_not_nan():
    assert _cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_keyword_overlap_exact_match():
    alias_index = _build_alias_index(_skills())
    assert _keyword_overlap_score(["Python"], ["Python"], alias_index) == 1.0


def test_keyword_overlap_alias_match():
    alias_index = _build_alias_index(_skills())
    # JD says "Postgres", bullet's skill is authored as "PostgreSQL" — same canonical skill.
    assert _keyword_overlap_score(["PostgreSQL"], ["Postgres"], alias_index) == 1.0


def test_keyword_overlap_no_match():
    alias_index = _build_alias_index(_skills())
    assert _keyword_overlap_score(["Python"], ["Java"], alias_index) == 0.0


def test_keyword_overlap_partial_match_is_fraction():
    alias_index = _build_alias_index(_skills())
    assert _keyword_overlap_score(["Python"], ["Python", "Java"], alias_index) == 0.5


def test_keyword_overlap_no_must_haves_is_zero():
    alias_index = _build_alias_index(_skills())
    assert _keyword_overlap_score(["Python"], [], alias_index) == 0.0


def _resume(limits=Limits(experience=1, projects=1, max_projects=1)) -> MasterResume:
    return MasterResume(
        contact=Contact(name="Test User", email="t@example.com"),
        limits=limits,
        education=[],
        experience=[
            Experience(
                id="exp1",
                title="Engineer",
                company="Acme",
                location="Remote",
                dates="2024",
                bullets=[
                    Bullet(id="b1", text="Worked with Python and PostgreSQL", skills=["Python", "PostgreSQL"]),
                    Bullet(id="b2", text="Wrote documentation", skills=[]),
                ],
            )
        ],
        projects=[
            Project(
                id="proj1",
                name="Side Project",
                tech=["Python"],
                dates="2024",
                bullets=[
                    Bullet(id="pb1", text="Built a Python tool", skills=["Python"]),
                ],
            ),
            Project(
                id="proj2",
                name="Other Project",
                tech=["Java"],
                dates="2023",
                bullets=[
                    Bullet(id="pb2", text="Built a Java tool", skills=["Java"]),
                ],
            ),
        ],
        skills=_skills(),
    )


def _fake_embed(texts: list[str]) -> list[list[float]]:
    # First text is always the JD query. Give Python-flavored text a vector
    # close to the JD, and everything else orthogonal, so ranking is deterministic.
    vectors = []
    for text in texts:
        vectors.append([1.0, 0.0] if "Python" in text or text == texts[0] else [0.0, 1.0])
    return vectors


def test_rank_resume_selects_higher_scoring_bullet_within_limit():
    resume = _resume()
    requirements = JobRequirements(company="Acme", title="Engineer", must_have_skills=["Python"])

    ranked = rank_resume(resume, requirements, jd_text="Looking for a Python engineer", embed_fn=_fake_embed)

    assert len(ranked.experience) == 1
    selected_ids = [rb.bullet.id for rb in ranked.experience[0].bullets]
    assert selected_ids == ["b1"]  # limits.experience=1, b1 scores higher (cosine + keyword)


def test_rank_resume_selects_top_project_by_score():
    resume = _resume()
    requirements = JobRequirements(company="Acme", title="Engineer", must_have_skills=["Python"])

    ranked = rank_resume(resume, requirements, jd_text="Looking for a Python engineer", embed_fn=_fake_embed)

    assert len(ranked.projects) == 1  # limits.max_projects=1
    assert ranked.projects[0].project.id == "proj1"


def test_drop_lowest_bullet_removes_lowest_scored():
    ranked = RankedResume(
        experience=[
            RankedExperience(
                experience=Experience(id="e", title="t", company="c", location="l", dates="d", bullets=[]),
                bullets=[
                    RankedBullet(Bullet(id="high", text="high", skills=[]), score=0.9),
                    RankedBullet(Bullet(id="low", text="low", skills=[]), score=0.1),
                ],
            )
        ],
        projects=[],
    )

    assert drop_lowest_bullet(ranked) is True
    remaining_ids = [rb.bullet.id for rb in ranked.experience[0].bullets]
    assert remaining_ids == ["high"]


def test_drop_lowest_bullet_returns_false_when_empty():
    ranked = RankedResume(experience=[], projects=[])
    assert drop_lowest_bullet(ranked) is False
