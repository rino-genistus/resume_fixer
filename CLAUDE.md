# Resume Tailor

Local web app: paste a job description (or a job URL) and get back a one-page PDF resume, in Jake's Resume format, tailored to pass ATS keyword screening. Single user (me). Goal is speed to submitting applications. Ship the MVP first, then polish.

## Non-negotiables
1. **No fabrication.** The LLM selects, reorders, and rephrases content from `data/master_resume.yaml`. It never invents skills, tools, employers, metrics, or dates. `validate.py` enforces this in code; don't rely on the prompt alone.
2. **No PII to the LLM.** The `contact` block is never included in any prompt. It is injected only at render time.
3. **One page.** Compile, count pages, drop the lowest-ranked bullet, recompile. Loop until the PDF is one page.
4. **ATS-parseable PDF.** Compile with `pdflatex` (TeX Live), not tectonic or XeLaTeX, because the template relies on `\pdfgentounicode=1`. Every build runs `pdftotext` and checks that the text extracts in order and contains the name and section headings.

## Stack
- Backend: Python 3.12, FastAPI, Pydantic, Jinja2, LiteLLM (provider-agnostic), pypdf
- LLM: Gemini API free tier by default (`LLM_MODEL=gemini/<model-id>` in `.env`). Swappable via LiteLLM to `ollama/qwen3:8b` or `anthropic/...` with no code changes.
- Embeddings: set by `EMBED_MODEL` (Gemini embedding model by default; `ollama/nomic-embed-text` when running locally).
- Free-tier rate limits are per project and low (check AI Studio). `llm.py` must retry on 429 with exponential backoff and respect an `LLM_RPM` setting from `.env`.
- Frontend: React + Vite + Tailwind, a single page
- LaTeX: TeX Live `pdflatex`

## Pipeline (`backend/pipeline/`)
1. `ingest.py`: take pasted text directly. For URLs, use the public JSON APIs where available (Greenhouse `boards-api.greenhouse.io`, Lever `api.lever.co/v0/postings`, Ashby). For anything else, try `httpx` + `trafilatura`. On failure, return an error that asks for pasted text. Don't scrape LinkedIn or Workday.
2. `extract.py`: turn the JD into a `JobRequirements` JSON (schema in `prompts/extract_jd.md`), using LiteLLM with JSON mode and temperature 0.
3. `rank.py`: score each bullet with 0.6 × cosine similarity (embeddings) + 0.4 × must-have keyword overlap. Select the top bullets per role or project within the limits in `master_resume.yaml`.
4. `rewrite.py`: rewrite ALL selected bullets in ONE LLM call (`prompts/rewrite_bullet.md`, returns a JSON array keyed by bullet id), temperature 0.2. This keeps each run to about 2 LLM calls, which stays well under free-tier limits. Keep a per-bullet mode behind `REWRITE_MODE=per_bullet` for small local models.
5. `validate.py`: reject a rewrite, and fall back to the original bullet, if it:
   - contains any number not in the source bullet, or
   - contains any JD keyword or skill term that is not in the source bullet's `skills` or the master `skills` list (aliases count).
6. `skills.py`: reorder skill categories and items so JD matches come first. Only include skills that are in the master list. No LLM.
7. `render.py`: fill the Jinja2 template with LaTeX-safe delimiters, escape every inserted string, compile with pdflatex, run the one-page loop and the ATS text check.
8. `report.py`: produce a keyword coverage report listing must-haves matched, must-haves missing, and nice-to-haves matched.

## LaTeX template
- Get `resume.tex` from github.com/jakegut/resume (MIT license; keep the license notice) and convert it to `templates/jake.tex.j2`.
- Jinja delimiters: `((* *))` for blocks, `((( )))` for variables, `((# #))` for comments.
- `latex_escape()` must handle `& % $ # _ { } ~ ^ \`. Unit-test it with inputs like "C#", "R&D", "50%", and "node_modules".
- Keep the template's standard headings exactly: Education, Experience, Projects, Technical Skills.

## ATS rules (apply in the prompts and in code)
- Use the JD's exact wording for skills the candidate has, e.g. "PostgreSQL" rather than "Postgres" when the JD says PostgreSQL.
- Write both forms of an acronym once, e.g. "Amazon Web Services (AWS)", when the JD uses either.
- No keyword stuffing. Each keyword appears where it is true; no hidden text, no keyword dumps.
- Single column, no tables or graphics, standard headings. Jake's template already satisfies this.
- Output filename: `FirstName_LastName_Resume.pdf`.

## Output
Each run writes to `output/{company}_{role}_{YYYY-MM-DD}/`: `resume.pdf`, `resume.tex`, `jd.txt`, `requirements.json`, and `report.json` (coverage, rejected rewrites, dropped bullets).

## API
- `POST /tailor {jd_text?, jd_url?}` returns `{run_id, pdf_url, report}`
- `GET /runs` lists past runs (this doubles as an application log)
- `GET /runs/{id}/pdf`

## UI (one page)
- A JD textarea or URL input, and a Tailor button
- A PDF preview (iframe) with a download button
- The coverage report, with missing must-haves highlighted. These tell me what to add to the master resume if they're true; the app never adds them.
- A side-by-side view of original vs rewritten bullets, with a per-bullet revert option, then re-render

## Build order
1. Schema + `latex_escape` + render the master resume as-is into a one-page PDF
2. Paste-only JD → extract → rank → render (no rewriting yet)
3. Rewrite + validate
4. Coverage report + UI
5. URL ingest

Out of scope for MVP: auth, database (the filesystem is enough), cover letters, LangGraph, evals.

## Conventions
- Put all LLM calls in `backend/llm.py`. Nothing else imports LiteLLM.
- Prompts live in `prompts/*.md`, loaded at runtime. Don't hardcode them in Python.
- pytest for escape, validate, rank, and the one-page loop.
- `data/master_resume.yaml`, `output/`, and `.env` are gitignored.
