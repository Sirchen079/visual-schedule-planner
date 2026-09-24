"""扫描页 OCR 管道：配置化的 openai_compat 视觉/OCR 模型（默认建议硅基流动
DeepSeek-OCR，任何 openai_compat 图片输入模型均可）。

流程：parse_file 检测出无文本层的扫描页（Markdown 里留「扫描页」占位节）→
ensure_parsed 落 pending 状态并经 ocr_kicker 钩子调度本模块 → 后台任务逐页
渲染 PNG（pypdfium2，已有依赖）调 OCR → 每页完成即替换占位节、重建 blocks
回填 extracted_text（中途可读、进度可见）→ 全部完成后 md_status=done。

失败模式：单页超时/报错保留占位并记警告；存在失败页时 md_status=failed
（资料库「重新解析」可重试）。密钥走 keyring（infra.secrets），设置里只存
base_url/model，不回显。"""
from __future__ import annotations

import asyncio
import io
import json
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

CONFIG_KEY = 'ocr_model_config'
KEY_REF = 'ocr_model'
PAGE_TIMEOUT = 90          # 单页 OCR 超时（秒）
MAX_OCR_PAGES = 200        # 单文件扫描页上限，超出部分保留占位并警告

_inflight: set[int] = set()
_futures: set = set()
_main_loop = None   # register() 在启动时捕获：kick 的调用方（工具线程池/to_thread）没有事件循环


def load_ocr_config(db) -> dict | None:
    """读取 OCR 模型配置；缺 base_url/model 或 key 视为未配置（返回 None）。"""
    from zhishi.domain import settingsvc
    from zhishi.infra.secrets import load_api_key
    try:
        raw = json.loads(settingsvc.get_setting(db, CONFIG_KEY, '') or '{}')
    except (ValueError, TypeError):
        return None
    cfg = {
        'base_url': str(raw.get('base_url') or '').strip().rstrip('/'),
        'model': str(raw.get('model') or '').strip(),
        'api_key': load_api_key(KEY_REF) or '',
    }
    if not cfg['base_url'] or not cfg['model'] or not cfg['api_key']:
        return None
    return cfg


def build_ocr_model(cfg: dict):
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider
    return OpenAIChatModel(cfg['model'], provider=OpenAIProvider(
        base_url=cfg['base_url'], api_key=cfg['api_key']))


OCR_PROMPT = (
    '把这张文档扫描页转换为 Markdown。规则：只输出页面正文内容本身，不要任何评论或前言；'
    '标题用 #/## 层级表示，表格用 Markdown 表格，列表保持列表；'
    '无法辨认的字符用▢占位，不要猜测补全；印刷模糊导致整行不可读时输出［无法辨认］。'
    '页眉、页脚、页码单独一行放在末尾。')


async def ocr_image(model, png: bytes) -> str:
    """单页图片 → Markdown 文本。模型侧幻觉是 OCR 的主要风险：提示词已禁猜，
    返回后过滤空结果。"""
    from pydantic_ai import Agent
    from pydantic_ai.messages import BinaryContent

    agent = Agent(model, output_type=str)
    result = await agent.run(['请转换为 Markdown。', BinaryContent(data=png, media_type='image/png')],
                             instructions=OCR_PROMPT)
    text = (result.output or '').strip()
    if not text:
        raise ValueError('OCR 返回空结果')
    return text


def _page_pattern(page: int) -> re.Pattern:
    return re.compile(rf'## 第 {page} 页（扫描页）\n.*?(?=\n## |\Z)', re.S)


def replace_page_section(markdown: str, page: int, text: str) -> str:
    """把占位节替换为 OCR 结果；占位节不在（如被 2M 截断）时追加到末尾。"""
    body = f'## 第 {page} 页（扫描页 · OCR）\n\n{text.strip()}'
    pattern = _page_pattern(page)
    if pattern.search(markdown):
        return pattern.sub(lambda _m: body, markdown, count=1)
    return markdown.rstrip() + '\n\n' + body


def _render_page(source: Path, page: int, resolution: int = 120) -> bytes:
    """渲染 PDF 页为 PNG（pypdfium2 经 pdfplumber，属既有依赖）。"""
    import pdfplumber

    with pdfplumber.open(str(source)) as pdf:
        image = pdf.pages[page - 1].to_image(resolution=resolution)
        buffer = io.BytesIO()
        image.original.save(buffer, format='PNG')
        return buffer.getvalue()


def _session_factory(db):
    return sessionmaker(bind=db.get_bind(), expire_on_commit=False)


def kick(db, file_id: int, storage_root: Path) -> None:
    """ensure_parsed 的调度钩子：已配置 OCR 且该文件未在转换中 → 投递后台任务。
    请求级 Session 只在 kick 内同步读配置，不进任务；从任意线程可安全调用。"""
    if file_id in _inflight or _main_loop is None or _main_loop.is_closed():
        return
    cfg = load_ocr_config(db)
    if cfg is None:
        return
    factory = _session_factory(db)
    _inflight.add(file_id)
    _spawn(_convert(factory, Path(storage_root), file_id, cfg))


def _spawn(coro) -> None:
    """把协程投递到主事件循环（线程安全；循环缺失时静默放弃，保持 pending
    由启动清扫 resume_pending 兜底）。"""
    if _main_loop is None or _main_loop.is_closed():
        coro.close()
        return
    future = asyncio.run_coroutine_threadsafe(coro, _main_loop)
    _futures.add(future)
    future.add_done_callback(_futures.discard)


async def _convert(factory, storage_root: Path, file_id: int, cfg: dict) -> None:
    from zhishi.adapters.parsers import doc_from_markdown
    from zhishi.domain.library import service
    from zhishi.domain.models import LibraryFile

    _inflight.add(file_id)
    failures: list[str] = []
    try:
        with factory() as db:
            file = db.get(LibraryFile, file_id)
            if file is None or file.deleted_at is not None or file.md_status != 'pending':
                return
            md_path = service.markdown_path(storage_root, file.storage_path)
            source = (storage_root.parent / file.storage_path).resolve()
            if not md_path.is_file() or not source.is_file():
                file.md_status = 'failed'
                db.commit()
                return
            kind = json.loads(file.extracted_text or '{}').get('kind', 'pdf')
            pending = json.loads(file.extracted_text or '{}').get('ocr_pages', [])[:MAX_OCR_PAGES]
            markdown = md_path.read_text(encoding='utf-8')
        model = build_ocr_model(cfg)
        for page in pending:
            try:
                png = await asyncio.to_thread(_render_page, source, page)
                text = await asyncio.wait_for(ocr_image(model, png), PAGE_TIMEOUT)
                markdown = replace_page_section(markdown, page, text)
            except Exception as exc:  # 单页失败不拖垮整篇；保留占位可重试
                failures.append(f'第 {page} 页：{str(exc)[:120]}')
                continue
            # 每页落盘回填：中途可读（read_material 每次读取重建索引，随读随新）
            with factory() as db:
                file = db.get(LibraryFile, file_id)
                if file is None or file.deleted_at is not None:
                    return
                service.write_markdown(storage_root, file.storage_path, markdown)
                failed_pages = [p for p in pending
                                if any(f.startswith(f'第 {p} 页：') for f in failures)]
                doc = doc_from_markdown(kind, markdown, warnings=[
                    f'第 {p} 页 OCR 未完成' for p in failed_pages])
                file.parse_status, file.extracted_text = 'parsed', doc.to_json()
                db.commit()
        with factory() as db:
            file = db.get(LibraryFile, file_id)
            if file is None or file.deleted_at is not None:
                return
            service.write_markdown(storage_root, file.storage_path, markdown)
            doc = doc_from_markdown(kind, markdown, warnings=[
                f'扫描页 OCR 失败（{"；".join(failures[:5])}）'] if failures else [])
            file.parse_status, file.extracted_text = 'parsed', doc.to_json()
            file.md_status = 'failed' if failures else 'done'
            db.commit()
    except Exception:
        # 任务级失败（如模型构造失败）：置 failed 让用户可重试，不吞异常不留死 pending
        with factory() as db:
            file = db.get(LibraryFile, file_id)
            if file is not None:
                file.md_status = 'failed'
                db.commit()
        import logging
        logging.getLogger(__name__).warning('扫描页 OCR 任务失败 file=%s', file_id, exc_info=True)
    finally:
        _inflight.discard(file_id)


def resume_pending(session_factory, storage_root: Path) -> int:
    """启动清扫：上次退出时滞留在 pending 的文件继续转换（幂等，in-flight 去重）。"""
    from zhishi.domain.models import LibraryFile
    resumed = 0
    with session_factory() as db:
        pending_ids = list(db.scalars(select(LibraryFile.id).where(
            LibraryFile.md_status == 'pending', LibraryFile.deleted_at.is_(None))))
        cfg = load_ocr_config(db)
        factory = _session_factory(db)
    if cfg is None:
        return 0
    for file_id in pending_ids:
        if file_id in _inflight:
            continue
        _inflight.add(file_id)
        _spawn(_convert(factory, Path(storage_root), file_id, cfg))
        resumed += 1
    return resumed


def register() -> None:
    """启动时挂接：注入 library.service 的调度钩子并捕获主事件循环
    （kick 从工具线程池/to_thread 调用，那里没有可用的 loop）。"""
    global _main_loop
    from zhishi.domain.library import service
    service.ocr_kicker = kick
    try:
        _main_loop = asyncio.get_running_loop()
    except RuntimeError:
        _main_loop = None
