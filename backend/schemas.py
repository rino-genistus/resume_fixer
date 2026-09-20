"""Pydantic models for LLM-produced structures (as opposed to models.py, which
mirrors the hand-authored master_resume.yaml)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class JobRequirements(BaseModel):
    company: str
    title: str
    seniority: Literal["intern", "new_grad", "junior", "mid", "senior", "unknown"] = "unknown"
    must_have_skills: list[str] = Field(default_factory=list)
    nice_to_have_skills: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    ats_keywords: list[str] = Field(default_factory=list)
