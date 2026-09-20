from backend.models import Bullet, Contact, Limits, MasterResume
from backend.pipeline import rewrite as rewrite_mod
from backend.schemas import JobRequirements


def _resume() -> MasterResume:
    return MasterResume(
        contact=Contact(name="Test User", email="t@example.com"),
        limits=Limits(experience=3, projects=3, max_projects=3),
        education=[],
        experience=[],
        projects=[],
        skills={},
    )


def _requirements() -> JobRequirements:
    return JobRequirements(company="Acme", title="Engineer")


def test_missing_bullet_id_falls_back_to_original(monkeypatch):
    bullets = [
        Bullet(id="b1", text="Original one", skills=[]),
        Bullet(id="b2", text="Original two", skills=[]),
    ]

    def fake_complete_json(prompt, *, temperature=0.0):
        # Only returns a rewrite for b1 — b2's id is missing from the response.
        return {"bullets": [{"id": "b1", "text": "Rewrote one", "keywords_used": []}]}

    monkeypatch.setattr(rewrite_mod, "complete_json", fake_complete_json)
    monkeypatch.setenv("REWRITE_MODE", "batch")

    result = rewrite_mod.rewrite_bullets(bullets, _resume(), _requirements())

    assert result["b1"]["text"] == "Rewrote one"
    assert result["b2"]["text"] == "Original two"  # fell back


def test_malformed_response_falls_back_all(monkeypatch):
    bullets = [Bullet(id="b1", text="Original one", skills=[])]

    def fake_complete_json(prompt, *, temperature=0.0):
        return {"unexpected_shape": True}

    monkeypatch.setattr(rewrite_mod, "complete_json", fake_complete_json)
    monkeypatch.setenv("REWRITE_MODE", "batch")

    result = rewrite_mod.rewrite_bullets(bullets, _resume(), _requirements())

    assert result["b1"]["text"] == "Original one"


def test_llm_exception_falls_back_all(monkeypatch):
    bullets = [Bullet(id="b1", text="Original one", skills=[])]

    def raising_complete_json(prompt, *, temperature=0.0):
        raise RuntimeError("boom")

    monkeypatch.setattr(rewrite_mod, "complete_json", raising_complete_json)
    monkeypatch.setenv("REWRITE_MODE", "batch")

    result = rewrite_mod.rewrite_bullets(bullets, _resume(), _requirements())

    assert result["b1"]["text"] == "Original one"


def test_batch_mode_makes_a_single_call(monkeypatch):
    bullets = [
        Bullet(id="b1", text="One", skills=[]),
        Bullet(id="b2", text="Two", skills=[]),
        Bullet(id="b3", text="Three", skills=[]),
    ]
    call_count = 0

    def fake_complete_json(prompt, *, temperature=0.0):
        nonlocal call_count
        call_count += 1
        return {"bullets": [{"id": b.id, "text": b.text, "keywords_used": []} for b in bullets]}

    monkeypatch.setattr(rewrite_mod, "complete_json", fake_complete_json)
    monkeypatch.setenv("REWRITE_MODE", "batch")

    rewrite_mod.rewrite_bullets(bullets, _resume(), _requirements())

    assert call_count == 1


def test_per_bullet_mode_makes_one_call_per_bullet(monkeypatch):
    bullets = [
        Bullet(id="b1", text="One", skills=[]),
        Bullet(id="b2", text="Two", skills=[]),
    ]
    call_count = 0

    def fake_complete_json(prompt, *, temperature=0.0):
        nonlocal call_count
        call_count += 1
        return {"bullets": [{"id": b.id, "text": b.text, "keywords_used": []} for b in bullets]}

    monkeypatch.setattr(rewrite_mod, "complete_json", fake_complete_json)
    monkeypatch.setenv("REWRITE_MODE", "per_bullet")

    rewrite_mod.rewrite_bullets(bullets, _resume(), _requirements())

    assert call_count == 2
