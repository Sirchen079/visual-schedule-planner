from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AIConfig, AISkill
from app.schemas import AISkillCreate, AISkillImport, AISkillUpdate


def list_skills(db: Session) -> list[AISkill]:
    return list(db.execute(select(AISkill).order_by(AISkill.updated_at.desc())).scalars().all())


def create_skill(db: Session, payload: AISkillCreate) -> AISkill:
    skill = AISkill(**payload.model_dump())
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return skill


def import_skill(db: Session, payload: AISkillImport) -> AISkill:
    suffix = Path(payload.filename).suffix.lower()
    if suffix not in {".md", ".txt"}:
        raise ValueError("只支持 .md / .txt skill")
    name = Path(payload.filename).stem or "自定义 skill"
    return create_skill(
        db,
        AISkillCreate(
            name=name,
            description="导入的自定义 skill",
            content=payload.content,
        ),
    )


def update_skill(db: Session, skill_id: int, payload: AISkillUpdate) -> AISkill | None:
    skill = db.get(AISkill, skill_id)
    if skill is None:
        return None
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(skill, field, value)
    db.commit()
    db.refresh(skill)
    return skill


def delete_skill(db: Session, skill_id: int) -> bool:
    skill = db.get(AISkill, skill_id)
    if skill is None:
        return False
    for config in db.execute(
        select(AIConfig).where(AIConfig.active_skill_id == skill_id)
    ).scalars().all():
        config.active_skill_id = None
    db.delete(skill)
    db.commit()
    return True


def enable_skill(db: Session, skill_id: int) -> AISkill | None:
    skill = db.get(AISkill, skill_id)
    if skill is None:
        return None
    for row in db.execute(select(AISkill)).scalars().all():
        row.enabled = row.id == skill_id
    for config in db.execute(
        select(AIConfig).where(AIConfig.enabled.is_(True))
    ).scalars().all():
        config.active_skill_id = skill_id
    db.commit()
    db.refresh(skill)
    return skill


def active_skill_text(db: Session, config: AIConfig | None) -> str:
    skill = None
    if config and config.active_skill_id:
        skill = db.get(AISkill, config.active_skill_id)
    if skill is None:
        skill = db.execute(
            select(AISkill).where(AISkill.enabled.is_(True))
        ).scalar_one_or_none()
    return skill.content if skill else ""
