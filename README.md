# Resume Tailor

A local web app: paste a job description (or a job URL) and get back a one-page PDF resume, in [Jake's Resume](https://github.com/jakegut/resume) LaTeX format, tailored to pass ATS keyword screening — without ever inventing skills, tools, employers, metrics, or dates you don't actually have.

Single-user, local-first. You keep a `master_resume.yaml` with *more* true bullets than fit on one page; for each job you paste, the app selects, reorders, and rephrases from that file — never adds to it.

Full design/spec lives in [CLAUDE.md](CLAUDE.md).

## How it works

```
JD text/URL
  → ingest.py     take pasted text directly (URL ingest: not yet built)
  → extract.py    JD → structured JobRequirements (LLM, JSON mode, temp 0)
  → rank.py       score every master-resume bullet: 0.6·cosine similarity + 0.4·keyword overlap
  → rewrite.py    reword selected bullets toward the JD's wording (LLM)
  → validate.py   reject any rewrite that adds a number/skill not in the source — keep the original instead
  → skills.py     reorder skill categories/items so JD matches surface first (no LLM)
  → render.py     fill the LaTeX template, compile with pdflatex, loop until it's one page
  → report.py     keyword coverage: must-haves matched/missing, nice-to-haves matched
```

Every run is written to `output/{company}_{role}_{date}/` (`resume.pdf`, `resume.tex`, `jd.txt`, `requirements.json`, `report.json`) — that directory listing doubles as your application log.

**Non-negotiables** (enforced in code, not just prompts):
- The LLM never sees your contact info — it's injected only at render/PDF time.
- `validate.py` rejects any rewrite that adds a number, skill, or JD keyword that isn't in the source bullet's skills or the master skills list (aliases count) — falls back to your original wording instead.
- The PDF is always exactly one page: compile → count pages → drop the lowest-ranked bullet → recompile, until it fits.
- Compiled with `pdflatex` (not tectonic/XeLaTeX) so `\pdfgentounicode=1` keeps the PDF text-extractable; every build runs `pdftotext` and checks your name and section headings extract in order.

## Prerequisites

- **Python 3.12+** (a venv is fine on later 3.x too)
- **TeX Live**, specifically `pdflatex` — install via [BasicTeX](https://www.tug.org/mactex/morepackages.html) (macOS, small) or your distro's `texlive` package. You'll also need these LaTeX packages if they're not already installed: `preprint` (for `fullpage.sty`), `titlesec`, `marvosym`, `enumitem` — via `tlmgr install preprint titlesec marvosym enumitem`.
- **poppler**, for `pdftotext` — `brew install poppler` (macOS) or `apt install poppler-utils` (Linux).
- **Node.js + npm**, for the frontend.
- An LLM provider — see [Configuring an LLM](#configuring-an-llm) below.

## Setup

```bash
# Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Your resume data (gitignored — this is your real, private data)
cp data/master_resume.example.yaml data/master_resume.yaml
# ...then edit data/master_resume.yaml: fill in contact info, education,
# experience, projects, and the skills list. Add MORE bullets than fit on
# one page — the app picks per job. Every bullet must be true.

# Environment
cp env.example .env
# ...then edit .env — see below.

# Frontend
cd frontend
npm install
cd ..
```

## Configuring an LLM

Set in `.env`. LiteLLM makes this provider-agnostic:

| Variable | Purpose |
|---|---|
| `LLM_MODEL` | Chat model for extraction + rewriting, e.g. `gemini/gemini-3.8-flash`, `ollama/qwen3:8b`, `anthropic/claude-haiku-4-5` |
| `EMBED_MODEL` | Embedding model for ranking, e.g. `gemini/gemini-embedding-001`, `ollama/nomic-embed-text` |
| `LLM_RPM` | Client-side rate limit (calls/minute) — set from your provider's free-tier limit |
| `LLM_THINKING_LEVEL` | Gemini 3.x only: `minimal`/`low`/`medium`/`high` |
| `REWRITE_MODE` | `batch` (all selected bullets in one LLM call — faster, fewer calls) or `per_bullet` (one call each — better for small local models) |
| `LLM_FALLBACK_MODEL` / `EMBED_FALLBACK_MODEL` | Automatic fallback if the primary fails after retries (e.g. a free-tier daily quota is exhausted). Falls back once per call, no `.env` editing needed mid-run. |
| `OLLAMA_API_BASE` | e.g. `http://localhost:11434`, needed if using any `ollama/...` model (primary or fallback) |
| `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` | API keys for the corresponding provider |

`env.example` has a ready-to-copy Gemini-free-tier-with-local-fallback setup. For local-only (no API key, no quota, slower): use `ollama/qwen3:8b` and `ollama/nomic-embed-text` for both the primary and fallback vars, run `ollama serve`, and `ollama pull qwen3:8b nomic-embed-text`.

## Running it

```bash
# Backend (from repo root, with .venv activated)
uvicorn backend.main:app --reload
# → http://127.0.0.1:8000

# Frontend (separate terminal)
cd frontend
npm run dev
# → http://localhost:5173 (proxies /tailor and /runs to the backend)
```

Open `http://localhost:5173`, paste a job description, click **Tailor**.

## Tests

```bash
source .venv/bin/activate
pytest
```

Covers `latex_escape`, the master-resume schema, ranking (cosine similarity, keyword overlap, alias matching, the one-page bullet-dropping loop), rewrite batching/fallback parsing, validation (fabricated numbers/skills, length limits, alias swaps), the coverage report, skill reordering, and the LLM fallback logic.

## Project layout

```
backend/
  main.py            FastAPI app: POST /tailor, GET /runs, GET /runs/{id}, GET /runs/{id}/pdf,
                      POST /runs/{id}/bullets/{bullet_id}/revert
  runs.py             Orchestrates the full pipeline; filesystem persistence under output/
  llm.py              The only module that imports litellm/google-genai
  models.py           Pydantic schema for master_resume.yaml
  schemas.py          Pydantic schema for LLM-extracted JobRequirements
  pipeline/
    ingest.py extract.py rank.py rewrite.py validate.py skills.py render.py report.py
data/
  master_resume.yaml           your real data (gitignored)
  master_resume.example.yaml   template to copy
prompts/
  extract_jd.md rewrite_bullet.md
templates/
  jake.tex.j2         Jinja2 LaTeX template (MIT-licensed, from github.com/jakegut/resume)
frontend/             React + Vite + Tailwind, single page
tests/
output/                gitignored; each run's PDF/tex/report lands here
```

## Status

Build order (see CLAUDE.md): schema/escape/render ✅ · paste-JD→extract→rank→render ✅ · rewrite+validate ✅ · coverage report + UI ✅ · URL ingest — not yet built (`POST /tailor` returns a 400 for `jd_url` in the meantime; paste the JD text instead).
