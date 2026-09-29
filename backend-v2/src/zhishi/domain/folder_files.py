"""对话文件夹域层：忽略规则、目录 walk、越权路径防护、限界读取与文档内存解析。

授权模型 = 对话附加动作本身：agent 层 _resolve_folder 从 DB 取附加根，本层只认路径几何——
含 `..` 段、绝对路径形态、或解析后逃出根（含 symlink 逃逸）一律 FolderPathError。
文档解析走 parse_file 纯内存，绝不在用户文件夹落 sidecar。搜索索引（任务 5）复用本文件
的常量与 walk，后续扩展追加在文件尾部，不改本节。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from zhishi.adapters.parsers import parse_file
from zhishi.domain.models import AIConversationFolder, FolderFileChunk

# ---- 忽略规则（规格 §10，大小写不敏感）----
# 目录：所有 `.` 开头目录一律忽略，另加以下清单（含点名冗余逐字保留）
IGNORED_DIRS = {"node_modules", "__pycache__", "venv", "env", "dist", "build", "target", "out",
                "bin", "obj", "coverage", ".next", ".nuxt", ".pytest_cache", ".mypy_cache",
                ".ruff_cache", ".turbo", ".parcel-cache"}

# 索引/直扫白名单后缀（仅这些进索引/直扫；任务 5 使用）
INDEX_TEXT_EXTS = {'.py', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs', '.vue', '.svelte', '.java',
                   '.c', '.cc', '.cpp', '.cxx', '.h', '.hh', '.hpp', '.cs', '.go', '.rs', '.rb',
                   '.php', '.swift', '.kt', '.kts', '.scala', '.sh', '.bash', '.zsh', '.ps1',
                   '.bat', '.cmd', '.md', '.markdown', '.txt', '.log', '.json', '.yaml', '.yml',
                   '.toml', '.ini', '.cfg', '.conf', '.xml', '.html', '.htm', '.css', '.scss',
                   '.less', '.sql', '.r', '.m'}

# 无后缀的常见文本文件名（同样进索引/直扫；`.env*` 按 `.env` 前缀匹配）
NO_EXT_TEXT_NAMES = {'Dockerfile', 'Makefile', 'LICENSE', 'README', 'CHANGELOG',
                     '.gitignore', '.env'}

# 读取黑名单（read/list 可见但 read 拒绝：二进制/媒体/压缩/字体）
BINARY_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.ico', '.tiff', '.exe', '.dll',
               '.so', '.dylib', '.bin', '.dat', '.zip', '.7z', '.rar', '.tar', '.gz', '.bz2',
               '.xz', '.jar', '.class', '.pyc', '.pyd', '.woff', '.woff2', '.ttf', '.otf',
               '.mp3', '.mp4', '.avi', '.mov', '.sqlite', '.db'}

# 文档后缀：走 parse_file 内存解析为 Markdown（绝不写 sidecar）
READ_DOC_EXTS = {'.pdf', '.docx', '.pptx', '.xlsx', '.csv'}

LIST_PAGE_SIZE = 500
READ_MAX_BYTES = 2 * 1024 * 1024   # read 硬上限 2MB
INDEX_MAX_BYTES = 512 * 1024       # 索引/直扫跳过 >512KB 的文本文件（任务 5 使用）
MAX_LINES_DEFAULT = 200
MAX_LINES_LIMIT = 500


class FolderPathError(ValueError):
    """路径越权/非法（`..` 段、绝对路径、symlink 逃逸）。"""


class FileTooLargeError(ValueError):
    """文件超过读取大小上限（2MB）。"""


def resolve_under_root(root: Path, rel: str) -> Path:
    """校验 rel 是根内相对路径（空串=根本身）并返回解析后的绝对路径；越权即 FolderPathError。"""
    text = (rel or "").strip().replace("\\", "/")
    if (text.startswith("/")
            or (len(text) > 1 and text[1] == ":")   # 盘符（C:/…）
            or ".." in text.split("/")):
        raise FolderPathError("只允许附加根内的相对路径")
    target = (root / text).resolve()
    if not target.is_relative_to(root.resolve()):
        raise FolderPathError("只允许附加根内的相对路径")
    return target


def _iter_tree(root: Path) -> Iterator[tuple[str, Path, int, float, bool]]:
    """递归产出 (rel_path, path, size, mtime, is_dir)；忽略规则过滤，rel_path 正斜杠。
    不跟随指向根外的目录链接（symlink/目录联接，防逃逸）；同一物理目录只进一次
    （visited 集合断根内环形联接，防无限递归）；OS 错误的子树跳过不中断。"""
    root_resolved = root.resolve()
    visited = {root_resolved}

    def rec(directory: Path, prefix: str) -> Iterator[tuple[str, Path, int, float, bool]]:
        try:
            entries = list(os.scandir(directory))
        except OSError:
            return
        for entry in entries:
            rel = prefix + entry.name
            try:
                if entry.is_dir(follow_symlinks=False):
                    if entry.name.lower() in IGNORED_DIRS or entry.name.startswith("."):
                        continue
                    dir_path = Path(entry.path)
                    resolved = dir_path.resolve()
                    if not resolved.is_relative_to(root_resolved):
                        continue   # 指向根外的目录链接：不列出也不深入
                    if resolved in visited:
                        continue   # 指向根内已访问目录的联接（环）：跳过
                    visited.add(resolved)
                    yield (rel, dir_path, 0, 0.0, True)
                    yield from rec(dir_path, rel + "/")
                elif entry.is_file(follow_symlinks=False):
                    stat = entry.stat()
                    yield (rel, Path(entry.path), stat.st_size, stat.st_mtime, False)
            except OSError:
                continue
    yield from rec(root, "")


def walk(root: Path) -> Iterator[tuple[str, Path, int, float]]:
    """递归产出文件 (rel_path, path, size, mtime)；忽略规则过滤，rel_path 正斜杠。"""
    for rel, path, size, mtime, is_dir in _iter_tree(root):
        if not is_dir:
            yield (rel, path, size, mtime)


def list_entries(root: Path, subdir: str, page: int) -> dict:
    """目录视图：基于 walk 的全树条目按 subdir 前缀过滤（文件与未忽略目录都出条目），
    按 rel_path 排序切页（500/页）。返回 {entries, page, next_page}，
    条目为 {name, rel_path, is_dir, size}（目录 size=0）。"""
    text = (subdir or "").strip().replace("\\", "/").strip("/")
    prefix = text + "/" if text else ""
    items: list[dict] = []
    for rel, path, _size, _mtime, is_dir in _iter_tree(root):
        if prefix and not rel.startswith(prefix):
            continue   # subdir 过滤：保留该子树
        name = rel.rsplit("/", 1)[-1]
        if is_dir:
            items.append({"name": name, "rel_path": rel, "is_dir": True, "size": 0})
        else:
            items.append({"name": name, "rel_path": rel, "is_dir": False, "size": _size})
    items.sort(key=lambda entry: entry["rel_path"])
    total_pages = max(1, -(-len(items) // LIST_PAGE_SIZE))
    page = max(1, int(page or 1))
    start = (page - 1) * LIST_PAGE_SIZE
    return {"entries": items[start:start + LIST_PAGE_SIZE],
            "page": page, "next_page": page + 1 if page < total_pages else None}


def read_text_bounded(path: Path) -> str:
    """限界读取文本（>2MB 拒绝）：utf-8-sig → gbk → utf-8(errors='replace') 三级回退。"""
    size = path.stat().st_size
    if size > READ_MAX_BYTES:
        raise FileTooLargeError(f"文件过大（{size / 1048576:.1f}MB），超过 2MB 读取上限")
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def read_doc_markdown(path: Path) -> str:
    """文档（pdf/docx/pptx/xlsx/csv）内存解析为 Markdown，绝不落 sidecar；
    unsupported/空正文时返回带说明的错误文本（扫描版 PDF 无文本层在此提示）。"""
    doc = parse_file(path)
    if doc.kind == 'unsupported' or not doc.markdown.strip():
        return ("未能解析出可读正文（可能是空文档或扫描版 PDF 无文本层）；"
                "请让用户确认文件内容。")
    return doc.markdown


# ---- 惰性关键词索引（任务 5）：缓存只加速搜索，必须先对账再出结果；----
# 读永远实时直读（read_folder_file 不走这里），索引不可用时直扫兜底——缓存可以慢、不能说谎。
CHUNK_LINES = 150                 # 每块行数（行号连续 line_start..line_end）
INDEX_BUILD_FILE_LIMIT = 2000     # 首建文件数上限：超过置 index_overflow 永久直扫
RECONCILE_CHANGE_LIMIT = 500      # 单次对账变更上限：超过放弃增量，本轮直扫
SEARCH_MATCH_LIMIT = 50           # 命中条数上限（超出 truncated=true）
SNIPPET_MAX_CHARS = 200           # 单条摘要最大字符数


def _is_indexable(rel_path: str) -> bool:
    """索引/直扫共用的可索引判断：后缀在 INDEX_TEXT_EXTS、或无后缀文件名在
    NO_EXT_TEXT_NAMES、或文件名以 `.env` 开头（`.env.local` 等 dotenv 变体，前缀语义）。"""
    name = rel_path.rsplit("/", 1)[-1]
    if name.startswith(".env"):
        return True
    dot = name.rfind(".")
    if dot <= 0:   # 无后缀（含 .gitignore 这类点名文件；rfind==0 说明整名以点开头）
        return name in NO_EXT_TEXT_NAMES
    return name[dot:].lower() in INDEX_TEXT_EXTS


def _chunk_file(db: Session, folder_id: int, path: Path, rel: str,
                mtime: float, size: int) -> None:
    """把一个文件按 CHUNK_LINES 行/块写入 chunk 行（mtime/size 冗余随行）；读失败跳过不中断。"""
    try:
        text = read_text_bounded(path)
    except OSError:
        return   # 权限/消失等 OS 错误：本轮跳过，下轮对账仍会视作变更重试
    lines = text.splitlines()
    for start in range(0, len(lines), CHUNK_LINES):
        seg = lines[start:start + CHUNK_LINES]
        db.add(FolderFileChunk(folder_id=folder_id, rel_path=rel, mtime=mtime, size=size,
                               line_start=start + 1, line_end=start + len(seg),
                               content="\n".join(seg)))


def _snapshot(root: Path) -> dict[str, tuple[float, int]]:
    """walk 快照：rel_path → (mtime, size)，只收可索引且 ≤INDEX_MAX_BYTES 的文件。"""
    return {rel: (mtime, size) for rel, _path, size, mtime in walk(root)
            if size <= INDEX_MAX_BYTES and _is_indexable(rel)}


def _ensure_index(db: Session, folder_row) -> bool:
    """惰性对账（新鲜度纪律核心）：walk 快照 vs 索引按 rel_path 聚合对比，
    新增/变更重分块、消失删行。返回索引是否可用（False = 调用方应直扫）。
    首建超 INDEX_BUILD_FILE_LIMIT 置 index_overflow 永久直扫；
    对账变更超 RECONCILE_CHANGE_LIMIT 放弃增量（索引保留原状），本轮直扫。"""
    root = Path(folder_row.root_path)
    snapshot = _snapshot(root)
    existing = list(db.scalars(select(FolderFileChunk)
                               .where(FolderFileChunk.folder_id == folder_row.id)))
    if not existing:   # 首建（该 folder 零行）
        if len(snapshot) > INDEX_BUILD_FILE_LIMIT:
            folder_row.index_overflow = True
            db.commit()
            return False
        for rel, (mtime, size) in snapshot.items():
            _chunk_file(db, folder_row.id, root / rel, rel, mtime, size)
        db.commit()
        return True
    by_rel: dict[str, tuple[float, int, list[FolderFileChunk]]] = {}
    for r in existing:
        by_rel.setdefault(r.rel_path, (r.mtime, r.size, []))[2].append(r)
    changed = [rel for rel, (mtime, size) in snapshot.items()
               if rel not in by_rel or by_rel[rel][:2] != (mtime, size)]
    removed = [rel for rel in by_rel if rel not in snapshot]
    if len(changed) + len(removed) > RECONCILE_CHANGE_LIMIT:
        return False   # 放弃增量：索引保留原状，本轮直扫兜底
    for rel in removed:
        for r in by_rel[rel][2]:
            db.delete(r)
    for rel in changed:
        for r in by_rel.get(rel, (0.0, 0, []))[2]:
            db.delete(r)
        mtime, size = snapshot[rel]
        _chunk_file(db, folder_row.id, root / rel, rel, mtime, size)
    db.commit()
    return True


def _collect_hits(rel_path: str, text: str, keyword: str, base_line: int,
                  out: list[dict]) -> None:
    """把 text 中的字面命中追加到 out（一行一条；line_no = base_line + 命中位置前换行数，
    snippet 取命中行，去首尾空白并截断）。上限外交由 _pack 截断。"""
    seen_lines: set[int] = set()
    pos = text.find(keyword)
    while pos >= 0:
        line_no = base_line + text.count("\n", 0, pos)
        if line_no not in seen_lines:
            seen_lines.add(line_no)
            line_begin = text.rfind("\n", 0, pos) + 1
            line_end = text.find("\n", pos)
            if line_end < 0:
                line_end = len(text)
            out.append({"rel_path": rel_path, "line_no": line_no,
                        "snippet": text[line_begin:line_end].strip()[:SNIPPET_MAX_CHARS]})
        pos = text.find(keyword, pos + len(keyword))


def _pack(matches: list[dict]) -> dict:
    """按 SEARCH_MATCH_LIMIT 截断并给出 total/truncated。"""
    truncated = len(matches) > SEARCH_MATCH_LIMIT
    return {"matches": matches[:SEARCH_MATCH_LIMIT],
            "total": min(len(matches), SEARCH_MATCH_LIMIT), "truncated": truncated}


def _search_scan(root: Path, keyword: str) -> dict:
    """直扫兜底：walk + read_text_bounded 逐文件实时找关键词（与索引同受大小/条数上限）。"""
    matches: list[dict] = []
    files = sorted((rel, path) for rel, path, size, _mtime in walk(root)
                   if size <= INDEX_MAX_BYTES and _is_indexable(rel))
    for rel, path in files:
        if len(matches) > SEARCH_MATCH_LIMIT:
            break   # 已超上限：不必继续读盘
        try:
            text = read_text_bounded(path)
        except OSError:
            continue
        _collect_hits(rel, text, keyword, 1, matches)
    return _pack(matches)


def _search_index(db: Session, folder_id: int, keyword: str) -> dict:
    """查已对账的索引块：字面子串命中 content，从命中位置回算行号。"""
    matches: list[dict] = []
    chunks = db.scalars(select(FolderFileChunk)
                        .where(FolderFileChunk.folder_id == folder_id)
                        .order_by(FolderFileChunk.rel_path, FolderFileChunk.id))
    for chunk in chunks:
        if len(matches) > SEARCH_MATCH_LIMIT:
            break
        _collect_hits(chunk.rel_path, chunk.content, keyword, chunk.line_start, matches)
    return _pack(matches)


def search_files(db: Session, folder_row, keyword: str) -> dict:
    """搜索唯一入口：先对账（索引只加速、必须新鲜），索引不可用时实时直扫兜底。
    返回 {ok, matches:[{rel_path, line_no, snippet}], total, truncated, mode:'index'|'scan'}。"""
    if not (keyword or "").strip():
        return {"ok": False, "error": "keyword 不能为空", "matches": [], "total": 0,
                "truncated": False, "mode": "scan"}
    if not folder_row.index_overflow and _ensure_index(db, folder_row):
        return {"ok": True, **_search_index(db, folder_row.id, keyword), "mode": "index"}
    return {"ok": True, **_search_scan(Path(folder_row.root_path), keyword), "mode": "scan"}


def purge_folder(db: Session, folder_id: int) -> None:
    """删该 folder 全部索引 chunk 行（移除附件与索引清理的统一入口，不依赖 FK 级联）。"""
    db.execute(delete(FolderFileChunk).where(FolderFileChunk.folder_id == folder_id))


def gc_orphans(session_factory) -> int:
    """启动 GC：删 folder_id 不在 ai_conversation_folders 的孤儿 chunk 行，返回删除数。"""
    with session_factory() as session:
        result = session.execute(
            delete(FolderFileChunk)
            .where(FolderFileChunk.folder_id.not_in(select(AIConversationFolder.id))))
        session.commit()
        return result.rowcount or 0
