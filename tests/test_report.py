from backend.models import Bullet, Contact, Experience, Limits, MasterResume, SkillItem
from backend.pipeline.rank import RankedBullet, RankedExperience, RankedResume
from backend.pipeline.report import build_coverage_report
from backend.pipeline.skills import reorder_skills
from backend.schemas import JobRequirements


def _resume() -> MasterResume:
    return MasterResume(
        contact=Contact(name="Test User", email="t@example.com"),
        limits=Limits(experience=3, projects=3, max_projects=3),
        education=[],
        experience=[],
        projects=[],
        skills={
            "Languages": [SkillItem(name="Python"), SkillItem(name="PostgreSQL", aliases=["Postgres"])],
            "Tools": [SkillItem(name="Docker")],
        },
    )


def _ranked_with_bullet(text: str) -> RankedResume:
    exp = Experience(id="e1", title="Eng", company="Acme", location="Remote", dates="2024", bullets=[])
    bullet = Bullet(id="b1", text=text, skills=["Python"])
    return RankedResume(
        experience=[RankedExperience(experience=exp, bullets=[RankedBullet(bullet, score=1.0)])],
        projects=[],
    )


def test_must_have_matched_via_bullet_text():
    resume = _resume()
    requirements = JobRequirements(company="Acme", title="Eng", must_have_skills=["Python"])
    ranked = _ranked_with_bullet("Built a service in Python")

    report = build_coverage_report(resume, ranked, requirements)

    assert report.must_haves_matched == ["Python"]
    assert report.must_haves_missing == []


def test_must_have_missing_when_absent():
    resume = _resume()
    requirements = JobRequirements(company="Acme", title="Eng", must_have_skills=["Kubernetes"])
    ranked = _ranked_with_bullet("Built a service in Python")

    report = build_coverage_report(resume, ranked, requirements)

    assert report.must_haves_missing == ["Kubernetes"]
    assert report.must_haves_matched == []


def test_must_have_matched_via_skills_section_alias():
    resume = _resume()
    # JD says "Postgres"; master resume's canonical name is "PostgreSQL", which
    # always renders in the Technical Skills section — should still count as covered.
    requirements = JobRequirements(company="Acme", title="Eng", must_have_skills=["Postgres"])
    ranked = _ranked_with_bullet("Built a service in Python")

    report = build_coverage_report(resume, ranked, requirements)

    assert report.must_haves_matched == ["Postgres"]


def test_nice_to_have_matched():
    resume = _resume()
    requirements = JobRequirements(company="Acme", title="Eng", nice_to_have_skills=["Docker"])
    ranked = _ranked_with_bullet("Built a service in Python")

    report = build_coverage_report(resume, ranked, requirements)

    assert report.nice_to_haves_matched == ["Docker"]


def test_reorder_skills_puts_jd_matches_first_within_category():
    resume = _resume()
    requirements = JobRequirements(company="Acme", title="Eng", must_have_skills=["PostgreSQL"])

    reordered = reorder_skills(resume, requirements)

    assert [i.name for i in reordered["Languages"]] == ["PostgreSQL", "Python"]


def test_reorder_skills_puts_matching_category_first():
    resume = _resume()
    requirements = JobRequirements(company="Acme", title="Eng", must_have_skills=["Docker"])

    reordered = reorder_skills(resume, requirements)

    assert list(reordered.keys())[0] == "Tools"


def test_reorder_skills_never_adds_or_removes_items():
    resume = _resume()
    requirements = JobRequirements(company="Acme", title="Eng", must_have_skills=["Kubernetes"])

    reordered = reorder_skills(resume, requirements)

    original_names = {i.name for items in resume.skills.values() for i in items}
    reordered_names = {i.name for items in reordered.values() for i in items}
    assert original_names == reordered_names
