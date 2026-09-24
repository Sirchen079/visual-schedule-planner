"""解析入口：Office/文本 → Markdown 结构化转换，PDF 按页提取并检测扫描页。

质量基线（PARSER_VERSION 3）：docx/pptx/xlsx/csv 先转 Markdown（标题层级、
表格、列表保留结构，见 markdown_convert），blocks 从 Markdown 按标题分节——
read_material 的引用位置与检索命中因此带章节路径。PDF 逐页提取文本，
无文本但有图像内容的页判为扫描页，页号记入 ocr_pages 交 OCR 管道补齐
（agent/ocr.py）；扫描页在 Markdown 里留占位节，OCR 完成后整篇重建 blocks。

ParsedDoc.markdown 仅用于落盘 sidecar（ensure_parsed 写 {原路径}.md），
不进 extracted_text——库列只存 blocks 预览，2M 上限的正文在磁盘。"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from itertools import islice
from pathlib import Path

from zhishi.adapters.markdown_convert import (
    csv_markdown, docx_markdown, extract_pipe_tables, feed_markdown_blocks,
    pptx_markdown, xlsx_markdown)

PARSER_VERSION = 3
MAX_CHARS = 30_000
MAX_TABLES, MAX_ROWS = 20, 60
MAX_DOCUMENT_CHARS, MAX_PAGES, MAX_DOCUMENT_ROWS = 2_000_000, 500, 50_000
BLOCK_CHARS = 2000
SCAN_PAGE_MIN_CHARS = 40   # 少于此字符且页面有图像内容 → 扫描页
IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}
MARKDOWN_EXTS = {'.docx', '.pptx', '.xlsx', '.csv'}


@dataclass
class ParsedDoc:
    kind: str
    text: str = ''
    tables: list[list[list[str]]] = field(default_factory=list)
    blocks: list[dict] = field(default_factory=list)
    parser_version: int = PARSER_VERSION
    partial: bool = False
    warnings: list[str] = field(default_factory=list)
    markdown: str = ''                    # 只落盘不进库（to_json 剔除）
    ocr_pages: list[int] = field(default_factory=list)   # 待 OCR 的扫描页页号

    def to_json(self) -> str:
        # Preview fields remain small; blocks hold the document body.
        if not self.blocks:
            builder = Blocks(self)
            builder.add('正文', self.text)
            for i, table in enumerate(self.tables):
                builder.add(f'表格 {i+1}', '\n'.join(' | '.join(row) for row in table))
        data = asdict(self)
        data.pop('markdown', None)
        data['text'], data['tables'] = self.text[:MAX_CHARS], self.tables[:MAX_TABLES]
        return json.dumps(data, ensure_ascii=False)


def doc_from_markdown(kind: str, markdown: str, warnings: list[str] | None = None) -> ParsedDoc:
    """从现成 Markdown（含 OCR 拼回的整篇）重建 ParsedDoc——OCR 任务补齐扫描页后
    用它重建 blocks 并回填缓存，不再碰原文件。"""
    doc = ParsedDoc(kind=kind, markdown=markdown[:MAX_DOCUMENT_CHARS],
                    warnings=list(warnings or []))
    doc.text = markdown[:MAX_CHARS]
    doc.tables = extract_pipe_tables(markdown, MAX_TABLES, MAX_ROWS)
    feed_markdown_blocks(markdown, Blocks(doc))
    return doc


class Blocks:
    def __init__(self, doc: ParsedDoc):
        self.doc, self.characters = doc, 0

    def warn(self, message: str):
        self.doc.partial = True
        if message not in self.doc.warnings:
            self.doc.warnings.append(message)

    def add(self, location: str, text: str):
        text = text.strip()
        available = MAX_DOCUMENT_CHARS - self.characters
        if len(text) > available:
            self.warn(f'解析正文达到 {MAX_DOCUMENT_CHARS} 字符上限，后续内容尚未处理。')
            text = text[:available]
        start = 0
        while start < len(text):
            end = min(start + BLOCK_CHARS, len(text))
            label = location if len(text) <= BLOCK_CHARS else f'{location} · 字符 {start+1}–{end}'
            self.doc.blocks.append({'location':label, 'text':text[start:end], 'overlap':120 if start else 0})
            if end == len(text):
                break
            start = end - 120
        self.characters += len(text)

    @property
    def full(self):
        return self.characters >= MAX_DOCUMENT_CHARS


def _trim(rows: list[list]) -> list[list[str]]:
    return [[('' if c is None else str(c)).strip() for c in row][:20] for row in rows[:MAX_ROWS]]


def parse_file(path: Path) -> ParsedDoc:
    ext = path.suffix.lower()
    if ext in IMAGE_EXTS:
        return ParsedDoc(kind='image')
    if ext in ('.txt', '.log', '.json'):
        with path.open(encoding='utf-8-sig', errors='replace') as source:
            text = source.read(MAX_DOCUMENT_CHARS+1)
        return doc_from_markdown('text', text)
    if ext in ('.md', '.markdown'):
        with path.open(encoding='utf-8-sig', errors='replace') as source:
            text = source.read(MAX_DOCUMENT_CHARS+1)
        return doc_from_markdown('text', text)   # kind 沿用 text：前端与既有缓存映射不破
    if ext == '.docx':
        markdown, warnings = docx_markdown(path)
        return _from_markdown('docx', markdown, warnings)
    if ext == '.pptx':
        markdown, warnings = pptx_markdown(path)
        return _from_markdown('pptx', markdown, warnings)
    if ext == '.xlsx':
        markdown, warnings = xlsx_markdown(path)
        return _from_markdown('xlsx', markdown, warnings)
    if ext == '.csv':
        markdown, _ = csv_markdown(path)
        return _from_markdown('csv', markdown, [])
    if ext == '.pdf':
        return _parse_pdf(path)
    return ParsedDoc(kind='unsupported')


def _from_markdown(kind: str, markdown: str, warnings: list[str]) -> ParsedDoc:
    doc = doc_from_markdown(kind, markdown, warnings)
    if not markdown.strip():
        doc.warnings.append('未转换出正文内容，文件可能是空文档或仅含不支持的结构。')
    return doc


def _parse_pdf(path: Path) -> ParsedDoc:
    import pdfplumber

    doc, previews, preview_chars = ParsedDoc(kind='pdf'), [], 0
    builder, md_parts = Blocks(doc), []
    with pdfplumber.open(str(path)) as source:
        if len(source.pages) > MAX_PAGES:
            builder.warn(f'PDF 超过 {MAX_PAGES} 页，后续页面尚未处理。')
        for number, page in enumerate(islice(source.pages, MAX_PAGES), 1):
            if builder.full:
                builder.warn('正文容量已满，后续页面尚未处理。')
                break
            text = (page.extract_text() or '').strip()
            if text:
                md_parts.append(f'## 第 {number} 页\n\n{text}')
                if preview_chars < MAX_CHARS:
                    previews.append(text)
                    preview_chars += len(text)
            elif page.images or page.curves or page.rects:
                # 无文本层但有图像内容：扫描页，OCR 管道补齐（未配置 OCR 时保留占位）
                doc.ocr_pages.append(number)
                md_parts.append(f'## 第 {number} 页（扫描页）\n\n（此页为扫描图像，等待 OCR 识别）')
            else:
                md_parts.append(f'## 第 {number} 页\n\n（本页无可提取文本）')
                builder.warn(f'第 {number} 页无可提取文本。')
            if number <= 5 and len(doc.tables) < MAX_TABLES:
                for table in (page.extract_tables() or [])[:MAX_TABLES-len(doc.tables)]:
                    doc.tables.append(_trim(table))
            page.close()
    if doc.ocr_pages:
        builder.warn(f'第 {", ".join(map(str, doc.ocr_pages[:10]))}'
                     f'{"…" if len(doc.ocr_pages) > 10 else ""} 页为扫描页，'
                     '已转交 OCR 识别；未配置 OCR 模型时这些页没有正文。')
    markdown = '\n\n'.join(md_parts)
    doc.markdown = markdown[:MAX_DOCUMENT_CHARS]
    doc.text = markdown[:MAX_CHARS]
    feed_markdown_blocks(markdown, builder)
    return doc
