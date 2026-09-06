"""Stable curriculum order; old projects fall back to their original task order."""
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from zhishi.domain.models import ResearchCurriculum, ResearchTask


def ordered_links(db: Session, project_id: int) -> list[ResearchTask]:
    links = list(db.scalars(select(ResearchTask).where(ResearchTask.project_id == project_id).order_by(ResearchTask.id)))
    saved = db.get(ResearchCurriculum, project_id, populate_existing=True)
    if saved is None:
        return links
    ids = json.loads(saved.order_json)
    by_id = {link.id:link for link in links}
    seen = set()
    result = []
    for lid in ids + list(by_id):
        if lid in by_id and lid not in seen:
            result.append(by_id[lid])
            seen.add(lid)
    return result


def save_order(db: Session, project_id: int, ids: list[int]) -> None:
    current = {link.id for link in ordered_links(db, project_id)}
    if len(ids) != len(set(ids)) or set(ids) != current:
        raise ValueError('课程顺序必须包含本项目的每条任务记录且不能重复')
    row = db.get(ResearchCurriculum, project_id)
    if row is None:
        row = ResearchCurriculum(project_id=project_id)
        db.add(row)
    row.order_json = json.dumps(ids)
