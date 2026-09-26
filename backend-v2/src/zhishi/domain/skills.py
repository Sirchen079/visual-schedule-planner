"""Reusable instructions and durable, separately readable source snapshots."""
from __future__ import annotations

import hashlib
import json

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from zhishi.domain.models import AISkill, AISkillPackage, AISkillResource, MaterialChunk

MAX_CONTENT = 30000
PAGE_SIZE = 6000


class SkillConflict(ValueError):
    pass


def get(db: Session, skill_id: int, *, enabled_only: bool = False) -> AISkill:
    row = db.get(AISkill, skill_id, populate_existing=True)
    if row is None or (enabled_only and not row.enabled):
        raise LookupError('技能不存在或已停用；请重新 search_skills 查询。')
    return row


def resources(db: Session, skill_id: int) -> list[AISkillResource]:
    return list(db.scalars(select(AISkillResource).where(AISkillResource.skill_id == skill_id)
                           .order_by(AISkillResource.id)))


def revision(db: Session, row: AISkill) -> str:
    package = db.get(AISkillPackage, row.id, populate_existing=True)
    value = [row.name, row.description, row.content, row.enabled,
             [(r.id, r.source_revision) for r in resources(db, row.id)],
             package.fingerprint if package else None]
    return hashlib.sha256(json.dumps(value, ensure_ascii=False).encode()).hexdigest()


def summary(row: AISkill) -> dict:
    return {key: getattr(row, key) for key in ('id', 'name', 'description', 'enabled', 'is_builtin')}


def detail(db: Session, skill_id: int, *, enabled_only: bool = False) -> dict:
    row = get(db, skill_id, enabled_only=enabled_only)
    package = db.get(AISkillPackage, skill_id, populate_existing=True)
    return {**summary(row), 'content': row.content, 'revision': revision(db, row),
            'files': json.loads(package.manifest_json) if package else [],
            'source': package.source if package else None,
            'resources': [{'id': r.id, 'name': r.name, 'source_file_id': r.source_file_id,
                           'characters': len(r.content), 'warnings': json.loads(r.warnings_json)}
                          for r in resources(db, skill_id)]}


def validate(name: str, description: str, content: str) -> tuple[str, str, str]:
    values = (name.strip(), description.strip(), content.strip())
    for label, value, maximum in zip(('名称', '用途描述', '正文'), values, (100, 2000, MAX_CONTENT)):
        if not value or len(value) > maximum:
            raise ValueError(f'技能{label}必填，最多 {maximum} 字。')
    return values


def snapshots(db: Session, file_ids: list[int], storage_root) -> list[dict]:
    """Parse before the skill transaction; no skill is created on partial failure."""
    from zhishi.domain.library import reading
    ids = list(dict.fromkeys(file_ids))
    if len(ids) > 10:
        raise ValueError('一个技能最多保存 10 份资料；请按用途拆分。')
    result = []
    total = 0
    for fid in ids:
        index = reading.ensure_index(db, fid, storage_root)
        info = reading.summary(db, fid)
        chunks = db.scalars(select(MaterialChunk).where(MaterialChunk.file_id == fid)
                            .order_by(MaterialChunk.part)).all()
        content = '\n\n'.join(f'【{c.location}】\n{c.content}' for c in chunks)
        total += len(content)
        if total > 500000:
            raise ValueError('技能资料快照合计最多 50 万字；请筛选相关文件或拆分技能。')
        warnings = list(info.get('warnings', []))
        if info.get('partial'):
            warnings.append('来源仅部分解析，快照不包含未解析内容。')
        result.append({'source_file_id': fid, 'name': info['name'], 'content': content,
                       'source_revision': index.revision,
                       'warnings_json': json.dumps(warnings, ensure_ascii=False)})
    return result


def write(db: Session, *, name: str, description: str, content: str,
          skill_id: int | None = None, expected_revision: str | None = None,
          enabled: bool | None = None, source_snapshots: list[dict] | None = None) -> AISkill:
    """Flush only: callers commit the skill, snapshots and AI receipt together."""
    name, description, content = validate(name, description, content)
    # Serialize SQLite writers before reading the revision / checking name uniqueness.
    db.connection().exec_driver_sql('UPDATE ai_skills SET id = id WHERE 0')
    row = get(db, skill_id) if skill_id is not None else None
    if row is not None:
        if row.is_builtin:
            raise ValueError('内置技能不可修改，请另存为自己的技能。')
        if not expected_revision or revision(db, row) != expected_revision:
            raise SkillConflict('技能已变化或缺少版本；请重新读取后再修改。')
    existing = db.scalar(select(AISkill).where(AISkill.name == name))
    if existing is not None and (row is None or existing.id != row.id):
        raise SkillConflict(f'已有同名技能 #{existing.id}；请读取后更新或使用不同名称。')
    if row is None:
        row = AISkill(name=name, enabled=True if enabled is None else enabled, is_builtin=False)
        db.add(row)
    content_changed = (row.name, row.description, row.content) != (name, description, content)
    row.name, row.description, row.content = name, description, content
    from zhishi.domain.skill_imports import sync_entrypoint
    if row.id is not None and content_changed:
        sync_entrypoint(db, row)
    if enabled is not None:
        row.enabled = enabled
    db.flush()
    if source_snapshots is not None:
        db.execute(delete(AISkillResource).where(AISkillResource.skill_id == row.id))
        db.add_all([AISkillResource(skill_id=row.id, **snapshot) for snapshot in source_snapshots])
        db.flush()
    return row


def read_resource(db: Session, skill_id: int, resource_id: int, offset: int = 0,
                  *, enabled_only: bool = False) -> dict:
    get(db, skill_id, enabled_only=enabled_only)
    row = db.get(AISkillResource, resource_id)
    if row is None or row.skill_id != skill_id:
        raise LookupError('该技能的资料不存在；请重新读取技能目录。')
    if offset < 0 or offset >= max(1, len(row.content)):
        raise ValueError('offset 超出资料范围。')
    end = offset + PAGE_SIZE
    return {'id': row.id, 'name': row.name, 'source_file_id': row.source_file_id,
            'source_revision': row.source_revision, 'text': row.content[offset:end],
            'offset': offset, 'total_characters': len(row.content),
            'warnings': json.loads(row.warnings_json),
            'next_offset': end if end < len(row.content) else None}
