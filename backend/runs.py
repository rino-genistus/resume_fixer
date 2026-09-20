"""Filesystem-backed run persistence and the end-to-end tailor orchestration
(ingest -> extract -> rank -> rewrite -> validate -> skills -> render ->
report). No database — the filesystem is enough for a single-user MVP
(CLAUDE.md); each run's directory under output/ doubles as the application log.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import date
from pathlib import Path

from backend.models import MasterResume, load_master_resume
from backend.pipeline.extract import extract_requirements
from backend.pipeline.ingest import ingest_pasted_text
from backend.pipeline.rank import RankedBullet, RankedExperience, RankedProject, RankedResume, rank_resume
from backend.pipeline.render import compile_pdf
from backend.pipeline.report import build_coverage_report
from backend.pipeline.rewrite import rewrite_bullets
from backend.pipeline.skills import reorder_skills
from backend.pipeline.validate import validate_rewrite
from backend.schemas import JobRequirements

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "output"
MASTER_RESUME_PATH = REPO_ROOT / "data" / "master_resume.yaml"


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_") or "unknown"


def _new_run_dir(company: str, role: str) -> Path:
    base = f"{_slug(company)}_{_slug(role)}_{date.today().isoformat()}"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    candidate = OUTPUT_DIR / base
    suffix = 2
    while candidate.exists():
        candidate = OUTPUT_DIR / f"{base}-{suffix}"
        suffix += 1
    candidate.mkdir(parents=True)
    return candidate


def _ranked_to_state(ranked: RankedResume) -> dict:
    return {
        "experience": [
            {
                "experience_id": re_.experience.id,
                "bullets": [{"id": rb.bullet.id, "score": rb.score} for rb in re_.bullets],
            }
            for re_ in ranked.experience
        ],
        "projects": [
            {
                "project_id": rp.project.id,
                "score": rp.score,
                "bullets": [{"id": rb.bullet.id, "score": rb.score} for rb in rp.bullets],
            }
            for rp in ranked.projects
        ],
    }


def _ranked_from_state(data: dict, resume: MasterResume) -> RankedResume:
    exp_by_id = {e.id: e for e in resume.experience}
    proj_by_id = {p.id: p for p in resume.projects}

    ranked_experience = []
    for entry in data["experience"]:
        exp = exp_by_id[entry["experience_id"]]
        bullet_by_id = {b.id: b for b in exp.bullets}
        bullets = [RankedBullet(bullet_by_id[b["id"]], b["score"]) for b in entry["bullets"] if b["id"] in bullet_by_id]
        ranked_experience.append(RankedExperience(exp, bullets))

    ranked_projects = []
    for entry in data["projects"]:
        proj = proj_by_id[entry["project_id"]]
        bullet_by_id = {b.id: b for b in proj.bullets}
        bullets = [RankedBullet(bullet_by_id[b["id"]], b["score"]) for b in entry["bullets"] if b["id"] in bullet_by_id]
        ranked_projects.append(RankedProject(proj, bullets, entry["score"]))

    return RankedResume(ranked_experience, ranked_projects)


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_report_payload(
    resume: MasterResume,
    ranked: RankedResume,
    requirements: JobRequirements,
    bullets: dict[str, dict],
    bullet_final_text: dict[str, str],
    dropped_bullet_ids: set[str],
) -> dict:
    coverage = build_coverage_report(resume, ranked, requirements, bullet_final_text)
    rejected = [
        {"bullet_id": bid, "original_text": b["original"], "reason": b["reason"]}
        for bid, b in bullets.items()
        if not b["accepted"]
    ]
    return {
        "coverage": asdict(coverage),
        "rejected_rewrites": rejected,
        "dropped_bullets": sorted(dropped_bullet_ids),
    }


def _selected_ids(ranked: RankedResume) -> set[str]:
    return {rb.bullet.id for re_ in ranked.experience for rb in re_.bullets} | {
        rb.bullet.id for rp in ranked.projects for rb in rp.bullets
    }


def create_run(jd_text: str) -> dict:
    jd_text = ingest_pasted_text(jd_text)
    resume = load_master_resume(MASTER_RESUME_PATH)
    requirements = extract_requirements(jd_text)

    ranked = rank_resume(resume, requirements, jd_text)
    selected_before_loop = _selected_ids(ranked)
    selected_bullets = [rb.bullet for re_ in ranked.experience for rb in re_.bullets] + [
        rb.bullet for rp in ranked.projects for rb in rp.bullets
    ]

    rewritten = rewrite_bullets(selected_bullets, resume, requirements)
    bullets: dict[str, dict] = {}
    for bullet in selected_bullets:
        rewritten_text = rewritten[bullet.id]["text"]
        result = validate_rewrite(bullet, rewritten_text, resume, requirements)
        bullets[bullet.id] = {
            "original": bullet.text,
            "rewritten": rewritten_text,
            "final": result.text,
            "accepted": result.accepted,
            "reason": result.reason,
        }

    skills = reorder_skills(resume, requirements)
    bullet_final_text = {bid: b["final"] for bid, b in bullets.items()}

    run_dir = _new_run_dir(requirements.company, requirements.title)
    run_id = run_dir.name

    compile_pdf(resume, ranked, run_dir, bullet_text=bullet_final_text, skills=skills)

    dropped_bullet_ids = selected_before_loop - _selected_ids(ranked)
    for bid in dropped_bullet_ids:
        bullets.pop(bid, None)

    (run_dir / "jd.txt").write_text(jd_text, encoding="utf-8")
    _write_json(run_dir / "requirements.json", requirements.model_dump())
    _write_json(
        run_dir / "report.json",
        _build_report_payload(resume, ranked, requirements, bullets, bullet_final_text, dropped_bullet_ids),
    )
    _write_json(
        run_dir / "state.json",
        {
            "run_id": run_id,
            "company": requirements.company,
            "title": requirements.title,
            "ranked": _ranked_to_state(ranked),
            "bullets": bullets,
        },
    )

    return get_run(run_id)


def _run_dir(run_id: str) -> Path:
    run_dir = OUTPUT_DIR / run_id
    if not run_dir.is_dir():
        raise FileNotFoundError(f"No such run: {run_id!r}")
    return run_dir


def list_runs() -> list[dict]:
    if not OUTPUT_DIR.is_dir():
        return []
    runs = []
    for run_dir in sorted(OUTPUT_DIR.iterdir(), reverse=True):
        state_path = run_dir / "state.json"
        if not state_path.is_file():
            continue
        state = _read_json(state_path)
        report_path = run_dir / "report.json"
        report = _read_json(report_path) if report_path.is_file() else {}
        runs.append(
            {
                "run_id": state["run_id"],
                "company": state["company"],
                "title": state["title"],
                "coverage": report.get("coverage"),
            }
        )
    return runs


def get_run(run_id: str) -> dict:
    run_dir = _run_dir(run_id)
    state = _read_json(run_dir / "state.json")
    report = _read_json(run_dir / "report.json")
    requirements = _read_json(run_dir / "requirements.json")
    jd_text = (run_dir / "jd.txt").read_text(encoding="utf-8")

    bullets = [{"bullet_id": bid, **info} for bid, info in state["bullets"].items()]

    return {
        "run_id": run_id,
        "company": state["company"],
        "title": state["title"],
        "jd_text": jd_text,
        "requirements": requirements,
        "report": report,
        "bullets": bullets,
    }


def run_pdf_path(run_id: str) -> Path:
    return _run_dir(run_id) / "resume.pdf"


def revert_bullet(run_id: str, bullet_id: str) -> dict:
    run_dir = _run_dir(run_id)
    state = _read_json(run_dir / "state.json")

    if bullet_id not in state["bullets"]:
        raise KeyError(f"No such bullet in this run: {bullet_id!r}")

    resume = load_master_resume(MASTER_RESUME_PATH)
    requirements = JobRequirements.model_validate(_read_json(run_dir / "requirements.json"))
    ranked = _ranked_from_state(state["ranked"], resume)
    skills = reorder_skills(resume, requirements)

    state["bullets"][bullet_id]["final"] = state["bullets"][bullet_id]["original"]
    state["bullets"][bullet_id]["accepted"] = True
    state["bullets"][bullet_id]["reason"] = "manually reverted"

    bullet_final_text = {bid: b["final"] for bid, b in state["bullets"].items()}
    compile_pdf(resume, ranked, run_dir, bullet_text=bullet_final_text, skills=skills)

    remaining_ids = _selected_ids(ranked)
    for bid in list(state["bullets"]):
        if bid not in remaining_ids:
            state["bullets"].pop(bid)

    _write_json(run_dir / "state.json", state)
    _write_json(
        run_dir / "report.json",
        _build_report_payload(resume, ranked, requirements, state["bullets"], bullet_final_text, set()),
    )

    return get_run(run_id)
