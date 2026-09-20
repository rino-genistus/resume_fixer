import json

import pytest

from backend import llm as llm_mod


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeCompletion:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeEmbeddingResponse:
    def __init__(self, vectors):
        self.data = [{"embedding": v} for v in vectors]


@pytest.fixture(autouse=True)
def _isolate_embed_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(llm_mod, "EMBED_CACHE_PATH", tmp_path / "embeddings.json")
    # Don't let the real LLM_RPM throttle these mocked, no-network calls.
    monkeypatch.setattr(llm_mod._rate_limiter, "min_interval", 0.0)


def test_complete_json_falls_back_on_primary_failure(monkeypatch):
    monkeypatch.setattr(llm_mod, "LLM_MODEL", "gemini/gemini-3.8-flash")
    monkeypatch.setattr(llm_mod, "LLM_FALLBACK_MODEL", "ollama/qwen3:8b")
    monkeypatch.setattr(llm_mod, "LLM_THINKING_LEVEL", None)

    calls = []

    def fake_completion(*, model, **kwargs):
        calls.append(model)
        if model == "gemini/gemini-3.8-flash":
            raise RuntimeError("simulated failure")
        return _FakeCompletion(json.dumps({"ok": True}))

    monkeypatch.setattr(llm_mod.litellm, "completion", fake_completion)

    result = llm_mod.complete_json("prompt", temperature=0.0)

    assert result == {"ok": True}
    assert "ollama/qwen3:8b" in calls
    assert calls[-1] == "ollama/qwen3:8b"  # the successful, final call


def test_complete_json_reraises_when_no_fallback_configured(monkeypatch):
    monkeypatch.setattr(llm_mod, "LLM_MODEL", "gemini/gemini-3.8-flash")
    monkeypatch.setattr(llm_mod, "LLM_FALLBACK_MODEL", None)
    monkeypatch.setattr(llm_mod, "LLM_THINKING_LEVEL", None)

    def always_fails(*, model, **kwargs):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(llm_mod.litellm, "completion", always_fails)

    with pytest.raises(RuntimeError, match="simulated failure"):
        llm_mod.complete_json("prompt", temperature=0.0)


def test_embed_falls_back_for_whole_batch_on_primary_failure(monkeypatch):
    monkeypatch.setattr(llm_mod, "EMBED_MODEL", "gemini/gemini-embedding-001")
    monkeypatch.setattr(llm_mod, "EMBED_FALLBACK_MODEL", "ollama/nomic-embed-text")

    def fake_embedding(*, model, input, **kwargs):
        if model == "gemini/gemini-embedding-001":
            raise RuntimeError("simulated failure")
        return _FakeEmbeddingResponse([[1.0, 0.0] for _ in input])

    monkeypatch.setattr(llm_mod.litellm, "embedding", fake_embedding)

    result = llm_mod.embed(["a", "b"])

    assert result == [[1.0, 0.0], [1.0, 0.0]]


def test_embed_falls_back_for_whole_batch_even_with_partial_primary_cache(monkeypatch):
    """If one text in the batch already has a valid primary-model cache entry
    but another doesn't and the primary is now down, both must come from the
    SAME (fallback) embedding space — mixing spaces within one similarity
    comparison would be meaningless."""
    monkeypatch.setattr(llm_mod, "EMBED_MODEL", "gemini/gemini-embedding-001")
    monkeypatch.setattr(llm_mod, "EMBED_FALLBACK_MODEL", "ollama/nomic-embed-text")

    def primary_embedding(*, model, input, **kwargs):
        return _FakeEmbeddingResponse([[9.0, 9.0] for _ in input])

    monkeypatch.setattr(llm_mod.litellm, "embedding", primary_embedding)
    llm_mod.embed(["a"])  # caches "a" under the primary model's key

    def primary_now_down(*, model, input, **kwargs):
        if model == "gemini/gemini-embedding-001":
            raise RuntimeError("simulated failure")
        return _FakeEmbeddingResponse([[1.0, 0.0] for _ in input])

    monkeypatch.setattr(llm_mod.litellm, "embedding", primary_now_down)
    result = llm_mod.embed(["a", "b"])  # "a" has a cached primary vector, "b" doesn't

    assert result == [[1.0, 0.0], [1.0, 0.0]]  # both from the fallback space, none mixed in


def test_embed_reraises_when_no_fallback_configured(monkeypatch):
    monkeypatch.setattr(llm_mod, "EMBED_MODEL", "gemini/gemini-embedding-001")
    monkeypatch.setattr(llm_mod, "EMBED_FALLBACK_MODEL", None)

    def always_fails(*, model, input, **kwargs):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(llm_mod.litellm, "embedding", always_fails)

    with pytest.raises(RuntimeError, match="simulated failure"):
        llm_mod.embed(["a"])
