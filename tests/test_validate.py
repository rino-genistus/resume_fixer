from backend.models import Bullet, Contact, Limits, MasterResume, SkillItem
from backend.pipeline.validate import validate_rewrite
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


def _requirements(**overrides) -> JobRequirements:
    defaults = dict(company="Acme", title="Engineer")
    defaults.update(overrides)
    return JobRequirements(**defaults)


def test_rejects_added_number():
    resume = _resume()
    requirements = _requirements()
    bullet = Bullet(id="b1", text="Improved API latency by 20%", skills=["Python"])

    result = validate_rewrite(bullet, "Improved API latency by 45%", resume, requirements)

    assert result.accepted is False
    assert "number" in result.reason
    assert result.text == bullet.text  # falls back to the original


def test_rejects_added_unauthorized_tool():
    resume = _resume()
    requirements = _requirements(ats_keywords=["Kubernetes"])
    bullet = Bullet(id="b1", text="Deployed the service to production", skills=["Python"])

    result = validate_rewrite(bullet, "Deployed the service to Kubernetes in production", resume, requirements)

    assert result.accepted is False
    assert "Kubernetes" in result.reason
    assert result.text == bullet.text


def test_accepts_valid_alias_swap():
    resume = _resume()
    requirements = _requirements(must_have_skills=["Postgres"])
    bullet = Bullet(id="b1", text="Built a service backed by Postgres", skills=["PostgreSQL"])

    result = validate_rewrite(bullet, "Built a service backed by PostgreSQL", resume, requirements)

    assert result.accepted is True
    assert result.text == "Built a service backed by PostgreSQL"


def test_rejects_length_overflow():
    resume = _resume()
    requirements = _requirements()
    bullet = Bullet(id="b1", text="Did a thing", skills=[])
    rewritten = "Did a thing " + "x" * 230

    result = validate_rewrite(bullet, rewritten, resume, requirements)

    assert result.accepted is False
    assert "230" in result.reason
    assert result.text == bullet.text


def test_accepts_unchanged_text():
    resume = _resume()
    requirements = _requirements()
    bullet = Bullet(id="b1", text="Did a thing", skills=[])

    result = validate_rewrite(bullet, "Did a thing", resume, requirements)

    assert result.accepted is True
