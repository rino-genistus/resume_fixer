"""Pydantic models for data/master_resume.yaml.

The `contact` block must never be passed into an LLM prompt (see CLAUDE.md).
Everything else here is fair game for ranking/rewriting.
"""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class Contact(BaseModel):
    name: str
    email: str
    location: str | None = None
    phone: str | None = None
    linkedin: str | None = None
    github: str | None = None
    website: str | None = None


class Limits(BaseModel):
    experience: int
    projects: int
    max_projects: int


class Bullet(BaseModel):
    id: str
    text: str
    skills: list[str] = Field(default_factory=list)


class Education(BaseModel):
    school: str
    location: str
    degree: str
    dates: str
    show_gpa: bool = False
    gpa: str | None = None
    coursework: list[str] = Field(default_factory=list)
    details: str | None = None


class Experience(BaseModel):
    id: str
    title: str
    company: str
    location: str
    dates: str
    bullets: list[Bullet]


class Project(BaseModel):
    id: str
    name: str
    tech: list[str] = Field(default_factory=list)
    dates: str
    link: str | None = None
    bullets: list[Bullet]


class SkillItem(BaseModel):
    name: str
    aliases: list[str] = Field(default_factory=list)


class MasterResume(BaseModel):
    contact: Contact
    limits: Limits
    education: list[Education]
    experience: list[Experience]
    projects: list[Project]
    skills: dict[str, list[SkillItem]]


def load_master_resume(path: Path) -> MasterResume:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return MasterResume.model_validate(data)
