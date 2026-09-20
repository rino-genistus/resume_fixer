"""Render the master resume into a one-page, ATS-parseable PDF (Jake's Resume template).

Compiles with pdflatex specifically (not tectonic/XeLaTeX) because the template
relies on \\pdfgentounicode=1 for ATS text extraction. See CLAUDE.md.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from pypdf import PdfReader

from backend.models import Education, MasterResume, SkillItem
from backend.pipeline.rank import RankedResume, drop_lowest_bullet

TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "templates"

SECTION_HEADINGS = ["Education", "Experience", "Projects", "Technical Skills"]

_LATEX_SPECIAL_CHARS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}
_LATEX_ESCAPE_RE = re.compile("|".join(re.escape(c) for c in _LATEX_SPECIAL_CHARS))


def latex_escape(text: str) -> str:
    """Escape LaTeX special characters in a single pass (avoids double-escaping
    backslashes introduced by earlier replacements)."""
    return _LATEX_ESCAPE_RE.sub(lambda m: _LATEX_SPECIAL_CHARS[m.group()], text)


def _jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        block_start_string="((*",
        block_end_string="*))",
        variable_start_string="(((",
        variable_end_string=")))",
        comment_start_string="((#",
        comment_end_string="#))",
        trim_blocks=True,
        lstrip_blocks=True,
        autoescape=False,
    )


def _education_detail(edu: Education) -> str | None:
    parts = []
    if edu.show_gpa and edu.gpa:
        parts.append(f"GPA: {edu.gpa}")
    if edu.coursework:
        parts.append("Coursework: " + ", ".join(edu.coursework))
    if edu.details:
        parts.append(edu.details)
    return "; ".join(parts) if parts else None


def build_context(
    resume: MasterResume,
    ranked: RankedResume,
    bullet_text: dict[str, str] | None = None,
    skills: dict[str, list[SkillItem]] | None = None,
) -> dict:
    """Build the Jinja context from the ranked bullet selection, escaping every
    inserted string for LaTeX. An entry that lost all its bullets (the one-page
    loop can empty one out) is omitted rather than rendered as a bare heading.

    `bullet_text` optionally overrides a bullet's rendered text by id (e.g.
    with the post-rewrite/validate text) without mutating the shared
    MasterResume/RankedResume objects. `skills` optionally overrides the
    category/item order (e.g. from skills.reorder_skills); defaults to
    resume.skills in master_resume.yaml's authored order.
    """
    bullet_text = bullet_text or {}
    skills = skills if skills is not None else resume.skills

    education = [
        {
            "school": latex_escape(e.school),
            "location": latex_escape(e.location),
            "degree": latex_escape(e.degree),
            "dates": latex_escape(e.dates),
            "detail": latex_escape(detail) if (detail := _education_detail(e)) else None,
        }
        for e in resume.education
    ]

    experience = [
        {
            "title": latex_escape(re_.experience.title),
            "company": latex_escape(re_.experience.company),
            "location": latex_escape(re_.experience.location),
            "dates": latex_escape(re_.experience.dates),
            "bullets": [latex_escape(bullet_text.get(rb.bullet.id, rb.bullet.text)) for rb in re_.bullets],
        }
        for re_ in ranked.experience
        if re_.bullets
    ]

    projects = [
        {
            "name": latex_escape(rp.project.name),
            "tech": latex_escape(", ".join(rp.project.tech)),
            "dates": latex_escape(rp.project.dates),
            "bullets": [latex_escape(bullet_text.get(rb.bullet.id, rb.bullet.text)) for rb in rp.bullets],
        }
        for rp in ranked.projects
        if rp.bullets
    ]

    # Built as one pre-joined LaTeX block (rather than looped in the template)
    # so the "\\" line-continuation between categories doesn't need a
    # blank-line trick that risks a stray \par inside \item{...}.
    skills_lines = [
        r"\textbf{%s}{: %s}" % (
            latex_escape(category),
            latex_escape(", ".join(item.name for item in items)),
        )
        for category, items in skills.items()
    ]
    skills_block = " \\\\\n     ".join(skills_lines)

    contact = resume.contact
    context_contact = {
        "name": latex_escape(contact.name),
        "email": latex_escape(contact.email),
        "phone": latex_escape(contact.phone) if contact.phone else None,
        "linkedin": latex_escape(contact.linkedin) if contact.linkedin else None,
        "github": latex_escape(contact.github) if contact.github else None,
        "website": latex_escape(contact.website) if contact.website else None,
    }

    return {
        "contact": context_contact,
        "education": education,
        "experience": experience,
        "projects": projects,
        "skills_block": skills_block,
    }


def render_tex(
    resume: MasterResume,
    ranked: RankedResume,
    bullet_text: dict[str, str] | None = None,
    skills: dict[str, list[SkillItem]] | None = None,
) -> str:
    env = _jinja_env()
    template = env.get_template("jake.tex.j2")
    return template.render(**build_context(resume, ranked, bullet_text, skills))


def count_pages(pdf_path: Path) -> int:
    return len(PdfReader(pdf_path).pages)


def check_ats_text(pdf_path: Path, name: str) -> str:
    """Run pdftotext and verify the name and section headings extract, in order.
    Guards against a PDF that looks right visually but an ATS can't parse."""
    if shutil.which("pdftotext") is None:
        raise RuntimeError("pdftotext not found. Install poppler (`brew install poppler`).")

    result = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    text = result.stdout

    positions = []
    for needle in [name, *SECTION_HEADINGS]:
        idx = text.find(needle)
        if idx == -1:
            raise RuntimeError(f"ATS check failed: {needle!r} did not extract from the PDF text layer.")
        positions.append(idx)

    if positions != sorted(positions):
        raise RuntimeError("ATS check failed: name/section headings did not extract in document order.")

    return text


def _pdflatex_pass(output_dir: Path, basename: str) -> None:
    for _ in range(2):  # two passes so hyperref/fancyhdr cross-references settle
        result = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", f"{basename}.tex"],
            cwd=output_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"pdflatex failed:\n{result.stdout[-4000:]}")


def compile_pdf(
    resume: MasterResume,
    ranked: RankedResume,
    output_dir: Path,
    basename: str = "resume",
    bullet_text: dict[str, str] | None = None,
    skills: dict[str, list[SkillItem]] | None = None,
) -> Path:
    """Write resume.tex, compile it with pdflatex, and enforce the one-page and
    ATS-parseability rules from CLAUDE.md: compile, count pages, drop the
    lowest-ranked bullet, recompile, until one page.
    """
    if shutil.which("pdflatex") is None:
        raise RuntimeError("pdflatex not found. Install TeX Live (not tectonic/XeLaTeX).")

    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = output_dir / f"{basename}.pdf"

    while True:
        tex_path = output_dir / f"{basename}.tex"
        tex_path.write_text(render_tex(resume, ranked, bullet_text, skills), encoding="utf-8")
        _pdflatex_pass(output_dir, basename)

        if count_pages(pdf_path) == 1:
            check_ats_text(pdf_path, name=resume.contact.name)
            return pdf_path

        if not drop_lowest_bullet(ranked):
            raise RuntimeError("Resume doesn't fit on one page even with every bullet dropped.")
