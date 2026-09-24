"""Office 文档 → Markdown 转换与 md 结构化分块。

质量要点：标题层级、列表、表格保留为 Markdown/HTML 结构（LLM 可读），
替代旧管道把段落拍平的纯文本流。图片一律不内嵌——base64 数据 URI 会
撑爆上下文，只留【图片】占位。扫描件 PDF 不在本层（见 agent/ocr.py）。

本模块只做格式转换，不触库不落盘；容量上限由调用方（parsers.Blocks）统一管。"""
from __future__ import annotations

import csv
import re
from pathlib import Path

_HEADING = re.compile(r'^(#{1,6})\s+(.+?)\s*#*\s*$', re.M)
_DOCX_HEADING_STYLE = re.compile(r'^(?:heading|标题)\s*(\d)', re.I)


def docx_markdown(path: Path) -> tuple[str, list[str]]:
    """docx → Markdown（python-docx 按文档流顺序走：标题样式 → # 层级、
    列表样式 → - 列表、表格 → 管道表；表格是课表/名单类文档的核心，
    不用 mammoth——它的 markdown 输出会把表格拍扁成段落）。"""
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    source = Document(str(path))
    out: list[str] = []
    for element in source.element.body:
        if element.tag.endswith('}p'):
            para = Paragraph(element, source)
            text = para.text.strip()
            if not text:
                continue
            try:
                style = (para.style.name or '') if para.style is not None else ''
            except Exception:
                style = ''
            match = _DOCX_HEADING_STYLE.match(style)
            if match:
                out.append(f"{'#' * min(int(match.group(1)), 6)} {text}")
            elif 'list' in style.lower() or '列表' in style:
                out.append(f'- {text}')
            else:
                out.append(text)
        elif element.tag.endswith('}tbl'):
            rows = [[cell.text.replace('\n', ' ').strip() for cell in row.cells]
                    for row in Table(element, source).rows]
            if rows:
                out.append(_pipe_table(rows))
    return '\n\n'.join(out), []


def pptx_markdown(path: Path, max_slides: int = 200) -> tuple[str, list[str]]:
    """pptx → Markdown：每页一节（标题、文本框、表格、备注）。"""
    from pptx import Presentation

    source = Presentation(str(path))
    warnings: list[str] = []
    sections: list[str] = []
    for number, slide in enumerate(source.slides, 1):
        if number > max_slides:
            warnings.append(f'幻灯片超过 {max_slides} 页，后续未转换。')
            break
        parts: list[str] = []
        title = ''
        try:
            title = (slide.shapes.title.text or '').strip() if slide.shapes.title is not None else ''
        except Exception:
            title = ''
        parts.append(f'## 幻灯片 {number}' + (f'：{title}' if title else ''))
        for shape in slide.shapes:
            if shape.has_table:
                rows = [[_cell_text(c) for c in row.cells] for row in shape.table.rows]
                parts.append(_pipe_table(rows))
            elif getattr(shape, 'has_text_frame', False) and shape.has_text_frame:
                body = '\n'.join(line.strip() for line in
                                 shape.text_frame.text.splitlines() if line.strip())
                if body and body != title:
                    parts.append(body)
        if slide.has_notes_slide:
            notes = (slide.notes_slide.notes_text_frame.text or '').strip()
            if notes:
                parts.append(f'**备注**：{notes}')
        sections.append('\n\n'.join(p for p in parts if p))
    return '\n\n'.join(sections), warnings


def xlsx_markdown(path: Path, max_sheets: int = 30, max_rows: int = 1000,
                  max_cols: int = 30) -> tuple[str, list[str]]:
    """xlsx → Markdown：每张工作表一节一张管道表。合并单元格用左上值填充；
    超出上限截断并提示。size 防线由调用方负责（read_only 无法读合并信息）。"""
    from openpyxl import load_workbook

    warnings: list[str] = []
    source = load_workbook(str(path), data_only=True)
    sections: list[str] = []
    try:
        for index, sheet in enumerate(source.worksheets, 1):
            if index > max_sheets:
                warnings.append(f'工作表超过 {max_sheets} 张，后续未转换。')
                break
            rows = _sheet_rows(sheet, max_rows, max_cols, warnings)
            if not rows:
                continue
            body = f'## 工作表「{sheet.title}」\n\n' + _pipe_table(rows)
            if sheet.max_row and sheet.max_row > max_rows:
                body += f'\n\n（共 {sheet.max_row} 行，仅展示前 {max_rows} 行）'
            sections.append(body)
    finally:
        source.close()
    return '\n\n'.join(sections), warnings


def _sheet_rows(sheet, max_rows: int, max_cols: int, warnings: list[str]) -> list[list[str]]:
    values = [list(row) for row in sheet.iter_rows(values_only=True, max_row=max_rows, max_col=max_cols)]
    if not values:
        return []
    for rng in getattr(sheet, 'merged_cells', None) and sheet.merged_cells.ranges or []:
        top_left = values[rng.min_row - 1][rng.min_col - 1] if (
            rng.min_row <= len(values) and rng.min_col <= len(values[0] or ())) else None
        for r in range(rng.min_row, min(rng.max_row, len(values)) + 1):
            row = values[r - 1]
            for c in range(rng.min_col, min(rng.max_col, len(row)) + 1):
                if not (r == rng.min_row and c == rng.min_col):
                    row[c - 1] = top_left
    # 去掉整行/整列为空的尾巴（扫描式大表的常见噪声）
    width = max((len([v for v in row if v not in (None, '')]) and
                 max(i + 1 for i, v in enumerate(row) if v not in (None, ''))
                 for row in values), default=0)
    values = [list(row[:width]) for row in values]
    while values and not any(v not in (None, '') for v in values[-1]):
        values.pop()
    return [['' if v is None else str(v) for v in row] for row in values]


def csv_markdown(path: Path, max_rows: int = 1000, max_cols: int = 30) -> tuple[str, list[str]]:
    rows: list[list[str]] = []
    with path.open(encoding='utf-8-sig', errors='replace', newline='') as source:
        for row in csv.reader(source):
            rows.append([str(c) for c in row[:max_cols]])
            if len(rows) >= max_rows:
                rows.append(['…', f'（超过 {max_rows} 行，后续未转换）'])
                break
    return (_pipe_table(rows) if rows else ''), []


def _pipe_table(rows: list[list[str]]) -> str:
    if not rows:
        return ''
    cells = [[str(c).replace('\n', ' ').replace('|', '\\|').strip() for c in row] for row in rows]
    width = max(len(r) for r in cells)
    cells = [r + [''] * (width - len(r)) for r in cells]
    head, body = cells[0], cells[1:]
    out = ['| ' + ' | '.join(head) + ' |', '|' + '|'.join([' --- '] * width) + '|']
    out += ['| ' + ' | '.join(r) + ' |' for r in body]
    return '\n'.join(out)


def _cell_text(cell) -> str:
    try:
        if getattr(cell, 'is_spanned', False):
            return ''
        return (cell.text or '').replace('\n', ' ').strip()
    except Exception:
        return ''


def split_sections(markdown: str) -> list[tuple[str, str]]:
    """按 Markdown 标题切节，返回 [(位置标签, 正文)]。无标题时整体一节「正文」；
    位置标签保留最近两级标题路径（如「第 2 章 · 数据来源」），供 read_material
    引用与检索命中展示。"""
    matches = list(_HEADING.finditer(markdown))
    if not matches:
        body = markdown.strip()
        return [('正文', body)] if body else []
    sections: list[tuple[str, str]] = []
    if matches[0].start() > 0:
        head = markdown[:matches[0].start()].strip()
        if head:
            sections.append(('正文（开头）', head))
    path: list[tuple[int, str]] = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        level, title = len(match.group(1)), match.group(2).strip()
        path = [p for p in path if p[0] < level]
        path.append((level, title))
        label = ' · '.join(t for _, t in path[-2:])
        body = markdown[match.end():end].strip()
        sections.append((label, body))
    return sections


def feed_markdown_blocks(markdown: str, builder) -> None:
    """md 分节灌入 parsers.Blocks（容量/重叠分块由 builder 统一管）。"""
    for label, body in split_sections(markdown):
        if body:
            builder.add(label, body)


def extract_pipe_tables(markdown: str, max_tables: int, max_rows: int) -> list[list[list[str]]]:
    """从 md 抽管道表格做 ParsedDoc.tables 预览。"""
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith('|') and stripped.endswith('|'):
            cells = [c.strip() for c in stripped.strip('|').split('|')]
            if all(re.fullmatch(r':?-{3,}:?', c) for c in cells if c):
                continue
            current.append(cells)
        elif current:
            tables.append(current[:max_rows])
            current = []
        if len(tables) >= max_tables:
            return tables
    if current and len(tables) < max_tables:
        tables.append(current[:max_rows])
    return tables
