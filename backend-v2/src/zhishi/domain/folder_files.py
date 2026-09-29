"""对话文件夹域层：忽略规则、目录 walk、越权路径防护、限界读取与文档内存解析。

授权模型 = 对话附加动作本身：agent 层 _resolve_folder 从 DB 取附加根，本层只认路径几何——
含 `..` 段、绝对路径形态、或解析后逃出根（含 symlink 逃逸）一律 FolderPathError。
文档解析走 parse_file 纯内存，绝不在用户文件夹落 sidecar。搜索索引（任务 5）复用本文件
的常量与 walk，后续扩展追加在文件尾部，不改本节。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

from zhishi.adapters.parsers import parse_file

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
