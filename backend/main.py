"""FastAPI app. URL ingest (jd_url) lands in build-order step 5 — POST /tailor
returns 400 for it until then."""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend import runs

app = FastAPI(title="Resume Tailor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class TailorRequest(BaseModel):
    jd_text: str | None = None
    jd_url: str | None = None


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/tailor")
def tailor(req: TailorRequest) -> dict:
    if req.jd_url:
        raise HTTPException(400, "URL ingestion isn't implemented yet — paste the job description text.")
    if not req.jd_text:
        raise HTTPException(400, "jd_text is required.")

    try:
        run = runs.create_run(req.jd_text)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc

    return {"run_id": run["run_id"], "pdf_url": f"/runs/{run['run_id']}/pdf", "report": run["report"]}


@app.get("/runs")
def list_runs() -> list[dict]:
    return runs.list_runs()


@app.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    try:
        return runs.get_run(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/runs/{run_id}/pdf")
def get_run_pdf(run_id: str) -> FileResponse:
    try:
        pdf_path = runs.run_pdf_path(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    if not pdf_path.is_file():
        raise HTTPException(404, "This run has no PDF.")
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=pdf_path.name,
        content_disposition_type="inline",
    )


@app.post("/runs/{run_id}/bullets/{bullet_id}/revert")
def revert_bullet(run_id: str, bullet_id: str) -> dict:
    try:
        return runs.revert_bullet(run_id, bullet_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
