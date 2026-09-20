from pathlib import Path

from backend.models import MasterResume, load_master_resume

EXAMPLE_PATH = Path(__file__).resolve().parent.parent / "data" / "master_resume.example.yaml"


def test_loads_example_resume():
    resume = load_master_resume(EXAMPLE_PATH)
    assert isinstance(resume, MasterResume)
    assert resume.contact.name == "First Last"
    assert resume.limits.max_projects == 3
    assert resume.experience[0].bullets[0].skills == ["Python", "FastAPI", "Snowflake", "Caching"]
    assert "Languages" in resume.skills
