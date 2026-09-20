"""JD ingestion. Paste-only for now — URL ingest (Greenhouse/Lever/Ashby/
httpx+trafilatura) lands in build-order step 5."""

MIN_JD_LENGTH = 50


def ingest_pasted_text(jd_text: str) -> str:
    text = jd_text.strip()
    if len(text) < MIN_JD_LENGTH:
        raise ValueError("Job description text is too short — paste the full posting.")
    return text
