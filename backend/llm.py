"""All LiteLLM (and, for the Gemini thinking-level fallback, google-genai) calls
live here. Nothing else in this codebase imports either SDK — pipeline modules
call complete_json()/embed().

If the primary model (LLM_MODEL/EMBED_MODEL) fails after retries — most often
a Gemini free-tier daily quota exhaustion — each call falls back once to
LLM_FALLBACK_MODEL/EMBED_FALLBACK_MODEL (local Ollama by default) so the app
keeps working instead of hard-failing until the quota resets.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import re
import time
from pathlib import Path

import litellm
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
EMBED_CACHE_PATH = CACHE_DIR / "embeddings.json"

LLM_MODEL = os.environ.get("LLM_MODEL", "ollama/qwen3:8b")
LLM_FALLBACK_MODEL = os.environ.get("LLM_FALLBACK_MODEL") or None
EMBED_MODEL = os.environ.get("EMBED_MODEL", "ollama/nomic-embed-text")
EMBED_FALLBACK_MODEL = os.environ.get("EMBED_FALLBACK_MODEL") or None
OLLAMA_API_BASE = os.environ.get("OLLAMA_API_BASE")
LLM_THINKING_LEVEL = os.environ.get("LLM_THINKING_LEVEL") or None
LLM_RPM = int(os.environ.get("LLM_RPM", "0") or "0")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

MAX_RETRIES = 5
BASE_RETRY_DELAY = 1.0


def load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def _api_base_for(model: str) -> str | None:
    return OLLAMA_API_BASE if model.startswith("ollama/") else None


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
    return text.strip()


# ---------------------------------------------------------------------------
# Rate limiting + retry
# ---------------------------------------------------------------------------


class _RateLimiter:
    """Enforces at most `rpm` calls/minute for a single-process, single-user app."""

    def __init__(self, rpm: int):
        self.min_interval = 60.0 / rpm if rpm > 0 else 0.0
        self._last_call = 0.0

    def wait(self) -> None:
        if self.min_interval <= 0:
            return
        remaining = self.min_interval - (time.monotonic() - self._last_call)
        if remaining > 0:
            time.sleep(remaining)
        self._last_call = time.monotonic()


_rate_limiter = _RateLimiter(LLM_RPM)


def _is_rate_limit_error(exc: Exception) -> bool:
    if isinstance(exc, litellm.RateLimitError):
        return True
    status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status_code == 429:
        return True
    return "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc)


def _call_with_retry(fn, *args, **kwargs):
    """Call fn, respecting LLM_RPM and retrying 429s with exponential backoff."""
    for attempt in range(MAX_RETRIES + 1):
        _rate_limiter.wait()
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            if not _is_rate_limit_error(exc) or attempt == MAX_RETRIES:
                raise
            delay = BASE_RETRY_DELAY * (2**attempt) + random.uniform(0, 0.5)
            time.sleep(delay)
    raise RuntimeError("unreachable")  # pragma: no cover


# ---------------------------------------------------------------------------
# Chat completion (JSON mode)
# ---------------------------------------------------------------------------


def _is_gemini_3_or_newer(model: str) -> bool:
    match = re.search(r"gemini-(\d+(?:\.\d+)?)", model)
    return bool(match) and float(match.group(1)) >= 3.0


def _litellm_supports_reasoning_effort(model: str) -> bool:
    """Whether the installed litellm version can pass thinking-level control
    through to this model (as its `reasoning_effort` param, which litellm maps
    to Gemini 3's `thinkingLevel`)."""
    try:
        provider, model_name = model.split("/", 1) if "/" in model else (None, model)
        params = litellm.get_supported_openai_params(model=model_name, custom_llm_provider=provider)
        return params is not None and "reasoning_effort" in params
    except Exception:
        return False


def _complete_via_litellm(
    model: str, prompt: str, temperature: float, *, reasoning_effort: str | None = None
) -> str:
    kwargs = dict(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        api_base=_api_base_for(model),
    )
    if reasoning_effort:
        kwargs["reasoning_effort"] = reasoning_effort
    try:
        response = _call_with_retry(litellm.completion, **kwargs, response_format={"type": "json_object"})
    except Exception:
        response = _call_with_retry(litellm.completion, **kwargs)
    return response.choices[0].message.content


def _complete_via_genai_sdk(model: str, prompt: str, temperature: float) -> str:
    """Fallback for when the installed litellm can't pass thinking_level
    through to Gemini 3.x: call Gemini directly via google-genai."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)
    model_name = model.split("/", 1)[1] if "/" in model else model
    config = types.GenerateContentConfig(
        temperature=temperature,
        response_mime_type="application/json",
        thinking_config=types.ThinkingConfig(thinking_level=LLM_THINKING_LEVEL) if LLM_THINKING_LEVEL else None,
    )
    response = _call_with_retry(client.models.generate_content, model=model_name, contents=prompt, config=config)
    return response.text


def _complete_json_with_model(model: str, prompt: str, temperature: float) -> dict:
    use_thinking_level = LLM_THINKING_LEVEL and model.startswith("gemini/") and _is_gemini_3_or_newer(model)

    if use_thinking_level and not _litellm_supports_reasoning_effort(model):
        content = _complete_via_genai_sdk(model, prompt, temperature)
    else:
        reasoning_effort = LLM_THINKING_LEVEL if use_thinking_level else None
        content = _complete_via_litellm(model, prompt, temperature, reasoning_effort=reasoning_effort)

    return json.loads(_strip_json_fences(content))


def complete_json(prompt: str, *, temperature: float = 0.0) -> dict:
    """Call the configured chat model and parse its response as JSON. Falls
    back once to LLM_FALLBACK_MODEL if the primary fails after retries."""
    try:
        return _complete_json_with_model(LLM_MODEL, prompt, temperature)
    except Exception as exc:
        if not LLM_FALLBACK_MODEL or LLM_FALLBACK_MODEL == LLM_MODEL:
            raise
        logger.warning("LLM_MODEL %r failed (%s) — falling back to %r", LLM_MODEL, exc, LLM_FALLBACK_MODEL)
        return _complete_json_with_model(LLM_FALLBACK_MODEL, prompt, temperature)


# ---------------------------------------------------------------------------
# Embeddings (batched, disk-cached by content hash)
# ---------------------------------------------------------------------------


def _cache_key(text: str, model: str) -> str:
    return hashlib.sha256(f"{model}:{text}".encode("utf-8")).hexdigest()


def _load_embed_cache() -> dict[str, list[float]]:
    if EMBED_CACHE_PATH.exists():
        return json.loads(EMBED_CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def _save_embed_cache(cache: dict[str, list[float]]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    EMBED_CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")


def _embed_with_model(texts: list[str], model: str, cache: dict[str, list[float]]) -> list[list[float]]:
    """Fetch every text's embedding from `model`, using/populating `cache`
    under that model's own key namespace. All vectors returned come from the
    same model, so callers can safely compare them (e.g. cosine similarity)."""
    keys = [_cache_key(t, model) for t in texts]
    missing = [i for i, k in enumerate(keys) if k not in cache]
    if missing:
        response = _call_with_retry(
            litellm.embedding,
            model=model,
            input=[texts[i] for i in missing],
            api_base=_api_base_for(model),
        )
        for i, item in zip(missing, response.data):
            cache[keys[i]] = item["embedding"]
        _save_embed_cache(cache)
    return [cache[k] for k in keys]


def embed(texts: list[str]) -> list[list[float]]:
    """Embed a batch of strings with the configured embedding model, reusing
    cached embeddings by content hash. On failure, falls back once to
    EMBED_FALLBACK_MODEL for the *whole* batch (not just what's missing from
    the primary's cache) — mixing vectors from two different embedding spaces
    in one similarity comparison would be meaningless.
    """
    cache = _load_embed_cache()
    try:
        return _embed_with_model(texts, EMBED_MODEL, cache)
    except Exception as exc:
        if not EMBED_FALLBACK_MODEL or EMBED_FALLBACK_MODEL == EMBED_MODEL:
            raise
        logger.warning("EMBED_MODEL %r failed (%s) — falling back to %r", EMBED_MODEL, exc, EMBED_FALLBACK_MODEL)
        return _embed_with_model(texts, EMBED_FALLBACK_MODEL, cache)
