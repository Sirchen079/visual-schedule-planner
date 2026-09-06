import json

from sqlalchemy.orm import Session

from zhishi.agent.tools.registry import ToolSpec, register
from zhishi.domain.library import reading


def _root(ctx):
    from zhishi.infra.config import get_settings
    return ctx.deps.storage_root or get_settings().attachments_dir


def read_material(db: Session, ctx, file_id: int, part: int = 1, count: int = 3, revision: str | None = None) -> str:
    """按编号读取长文件原文，每次最多5个片段。file_id来自附件/资料库/项目，part从1开始。
    返回页码或行号、版本和准确的下一段调用；需要全文总结时继续next_call，不把开头摘要当作已读全文。
    检索命中后使用返回的part和revision，引用保留位置及原文；图片需对话视觉输入。"""
    return json.dumps(reading.read(db, file_id, _root(ctx), part=part, count=count, revision=revision), ensure_ascii=False)


def search_materials(db: Session, ctx, query: str, file_id: int | None = None,
                     project_id: int | None = None, file_offset: int = 0, limit: int = 6) -> str:
    """在本地材料正文中检索关键词，不联网。可限定文件或学习项目；不提供范围则搜索资料库。
    query写1至8个短关键词，以空格隔开；每次检查20份文件，返回命中页码/行号和可直接read_material的参数。
    有更多文件时按next_call继续；检索片段不是完整阅读，不要据此声称读完所有文件。"""
    return json.dumps(reading.search(db, query, _root(ctx), file_id=file_id, project_id=project_id,
        file_offset=file_offset, limit=limit), ensure_ascii=False)


for fn in (read_material, search_materials):
    register(ToolSpec(fn.__name__, fn.__doc__ or '', 'readonly', None, fn))
