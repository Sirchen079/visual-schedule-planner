# 对话文件夹附件 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 subagent-driven-development（推荐）或 executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 用户在对话输入区把本地文件夹附加进会话，知时的代理用 4 个只读工具按需列出/读取/搜索其中文件。

**架构：** 新表 `ai_conversation_folders` + `folder_file_chunks`（随 create_all 建表）；领域层 `domain/folder_files.py` 承载全部文件系统访问（忽略规则、越权防护、限界读取、惰性索引）；工具层 `agent/tools/folder_tools.py` 只做薄 JSON 包装并经 registry/search_tools 发现；每轮 run 在用户消息尾部注入【对话文件夹】小块（零附加零注入）；REST 三端点 + Electron 目录选择 IPC + 前端按钮/chip。

**技术栈：** FastAPI + SQLAlchemy(SQLite) + pydantic-ai 工具注册表；Vue 3 + Pinia；Electron IPC。

**规格：** `docs/superpowers/specs/2026-09-29-conversation-folder-attachment-design.md`（本计划的论证依据；执行者必读，数值以规格为准）。

## 全局约束

- **本仓库工作区不是 git 仓库**。每个 Commit 步骤统一用以下流程（在 Git Bash 中执行；`<MSG>` 为该任务给出的提交信息，`<FILES>` 为该任务改动的文件相对路径清单）：
  ```bash
  TMP="$LOCALAPPDATA/Temp/zhishi-task-clone"; rm -rf "$TMP"
  git -c http.proxy=http://127.0.0.1:7897 clone --depth 1 https://github.com/Sirchen079/visual-schedule-planner "$TMP"
  # 逐个 cp 工作区改动文件到 "$TMP" 对应路径（mkdir -p 先建目录），然后：
  cd "$TMP" && git config user.name Sirchen079 && git config user.email "194774675+Sirchen079@users.noreply.github.com"
  git add -A && git commit -m "<MSG>" && git -c http.proxy=http://127.0.0.1:7897 push origin HEAD:main
  cd - && rm -rf "$TMP"
  ```
- 后端测试命令一律 `cd /e/知时-v2/backend-v2 && .venv/Scripts/python.exe -m pytest <目标> -v`（系统 python 无 pytest）。
- 前端测试 `cd /e/知时-v2/frontend-v2/app && npx vitest run <目标>`；DOM 测试文件顶部须 `// @vitest-environment jsdom`。
- **红线（规格 §14）**：新工具不进 CORE_TOOLS；`rest.d.ts` 不重生成（前端类型手写）；工具 docstring 保持克制短句，教学话术放校验错误/错误 JSON；零附加零注入。
- 数值逐字照抄规格：列表 500 条/页；read 默认 200 行、上限 500 行、单文件 2MB 硬上限；索引/直扫跳过 >512KB 文本；150 行/块；首建上限 2000 文件；对账变更 >500 放弃增量整轮直扫；搜索命中上限 50 条。忽略规则三张清单照抄规格 §10。
- 工具错误一律返回 `{"ok": false, "error": "…"}` JSON 文本（session_tools.py 风格），不 raise。

## 审查重点（Review Focus）

1. **路径逃逸**：`path`/`subdir` 含 `..`、绝对路径、或符号链接解析后落在附加根之外 → 必须拒绝且报"只读根内相对路径"（任务 2 测试钉死）。
2. **磁盘状态漂移**：附加的文件夹被用户删除/更名后调用任何工具 → 清晰错误提示让模型引导用户移除 chip，绝不抛未捕获异常（任务 2 测试钉死）。
3. **中文编码**：GBK 编码的代码/文本文件读取不乱码不失败（任务 2 用真实 GBK 字节样本钉死）。
4. **大仓库降级**：>2000 文件首建溢出、或对账变更 >500 → 降级直扫，不挂死不崩（任务 5 测试钉死）。
5. **绝不在用户文件夹落盘**：读 PDF/docx 走 parse_file 内存解析后，用户目录内不得出现任何 `.md` sidecar 或新文件（任务 2 测试钉死）。

---

### 任务 1：数据模型 + `list_folders` 工具 + 功能开关 + 守卫

**文件：**
- 修改：`backend-v2/src/zhishi/domain/models.py`（文件末尾，AIMemory 之后加两个类）
- 修改：`backend-v2/src/zhishi/domain/settingsvc.py`（DEFAULTS 字典）
- 创建：`backend-v2/src/zhishi/agent/tools/folder_tools.py`
- 修改：`backend-v2/src/zhishi/agent/tools/__init__.py`（加一行 import）
- 测试：`backend-v2/tests/agent/test_folder_tools.py`

- [ ] **步骤 1：编写失败的测试**（夹具照 `tests/agent/test_memory_tools.py` 的 `db(tmp_path)` 模式）

```python
"""对话文件夹工具：list_folders 语义、registry 开关门控、CORE_TOOLS 守卫。"""
import pytest
from sqlalchemy.orm import Session

from zhishi.agent.tools.folder_tools import FOLDER_FLAG, FOLDER_TOOLS, list_folders
from zhishi.agent.tools.registry import specs_for
from zhishi.agent.tool_discovery import CORE_TOOLS
from zhishi.domain import settingsvc
from zhishi.domain.models import AIConversation, AIConversationFolder


@pytest.fixture
def db(tmp_path):
    # 与 test_memory_tools.py 相同：make_engine + create_all + make_session_factory
    ...


def _conv(db) -> AIConversation:
    row = AIConversation(title="t"); db.add(row); db.commit(); db.refresh(row); return row


def test_list_folders_empty_teaches_attach(db):
    ctx = type("C", (), {"deps": type("D", (), {"conversation_id": 1})})()
    out = list_folders(db, ctx=ctx)   # type: ignore[arg-type]
    assert '"ok": false' in out and "附加" in out


def test_list_folders_lists_current_conversation_only(db):
    c1, c2 = _conv(db), _conv(db)
    db.add_all([AIConversationFolder(conversation_id=c1.id, root_path="E:/repo-a", label="repo-a"),
                AIConversationFolder(conversation_id=c2.id, root_path="E:/repo-b", label="repo-b")])
    db.commit()
    ctx = type("C", (), {"deps": type("D", (), {"conversation_id": c1.id})})()
    out = list_folders(db, ctx=ctx)   # type: ignore[arg-type]
    assert "repo-a" in out and "repo-b" not in out


def test_no_ctx_returns_error(db):
    assert '"ok": false' in list_folders(db)


def test_guard_not_in_core_tools_and_flag_gating(db):
    assert not FOLDER_TOOLS & CORE_TOOLS        # FOLDER_TOOLS 为最终四个名字的集合（本任务只注册 list_folders）
    names = {s.name for s in specs_for(db)}
    assert "list_folders" in names              # 默认开
    settingsvc.set_setting(db, FOLDER_FLAG, "false")
    assert "list_folders" not in {s.name for s in specs_for(db)}    # 关闭即下线
```

- [ ] **步骤 2：运行验证失败**：`.venv/Scripts/python.exe -m pytest tests/agent/test_folder_tools.py -v` → FAIL（ModuleNotFoundError: folder_tools）
- [ ] **步骤 3：实现**
  - `models.py` 照 AIMemory 的 `Mapped/mapped_column` 风格加：
    ```python
    class AIConversationFolder(Base):
        """对话附加的本地文件夹：附加即读取授权，移除即撤销。label 默认取文件夹名。"""
        __tablename__ = "ai_conversation_folders"
        id: Mapped[int] = mapped_column(primary_key=True)
        conversation_id: Mapped[int] = mapped_column(Integer, index=True)
        root_path: Mapped[str] = mapped_column(String(400))
        label: Mapped[str] = mapped_column(String(200))
        index_overflow: Mapped[bool] = mapped_column(Boolean, default=False)
        created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    class FolderFileChunk(Base):
        """对话文件夹搜索索引：150 行/块的内容块，mtime/size 冗余随行，按 rel_path 聚合对账。"""
        __tablename__ = "folder_file_chunks"
        id: Mapped[int] = mapped_column(primary_key=True)
        folder_id: Mapped[int] = mapped_column(Integer, index=True)
        rel_path: Mapped[str] = mapped_column(String(500))
        mtime: Mapped[float] = mapped_column(Float)
        size: Mapped[int] = mapped_column(Integer)
        line_start: Mapped[int] = mapped_column(Integer)
        line_end: Mapped[int] = mapped_column(Integer)
        content: Mapped[str] = mapped_column(Text)
    ```
  - `settingsvc.DEFAULTS` 加 `"feature_folder_tools_enabled": "true",  # 对话文件夹工具：默认开（零附加零成本）`
  - `folder_tools.py`：`FOLDER_FLAG = "feature_folder_tools_enabled"`、`FOLDER_TOOLS = {"list_folders", "list_folder_files", "read_folder_file", "search_folder_files"}`；`_cid(ctx)` 照 session_tools.py:18 的 `getattr(getattr(ctx, 'deps', None), 'conversation_id', None)`；`list_folders(db: Session, ctx=None) -> str` docstring 一句话"列当前对话附加的本地文件夹（名称与根路径）"，无会话/无附加时返回教用户附加的错误 JSON；文件底部照 memory_tools 的 `_FOLDER_SPECS = [ToolSpec(...)] + _install()`（本任务只注册 list_folders，safety='readonly'，flag=FOLDER_FLAG），`tools/__init__.py` 加 `from zhishi.agent.tools import folder_tools  # noqa: F401`
- [ ] **步骤 4：运行验证通过**（同步骤 2 命令）→ PASS 全绿
- [ ] **步骤 5：Commit**，信息：`feat: conversation folder data model and list_folders tool`

### 任务 2：`list_folder_files` + `read_folder_file`（领域层 folder_files + 全部防护）

**文件：**
- 创建：`backend-v2/src/zhishi/domain/folder_files.py`（忽略规则常量、walk、越权防护、限界读取）
- 修改：`backend-v2/src/zhishi/agent/tools/folder_tools.py`（两个新工具 + `_resolve_folder`）
- 测试：`backend-v2/tests/agent/test_folder_tools.py`（追加）、`backend-v2/tests/domain/test_folder_files.py`（新建）

- [ ] **步骤 1：编写失败的测试**（真实临时目录构造夹具）

```python
# tests/domain/test_folder_files.py 核心断言（夹具：tmp_path 下建 repo/，含 a.py、docs/readme.md、
# node_modules/junk.js、.git/config、big.bin(3MB)、gbk.txt(GBK 编码中文)、sub/inner.ts）
def test_walk_respects_ignore_rules(...):
    rels = [r for r, *_ in ff.walk(root)]
    assert "a.py" in rels and "sub/inner.ts" in rels
    assert not any(r.startswith(("node_modules/", ".git/")) for r in rels)

def test_resolve_under_root_rejects_escape(root):
    for bad in ("../x", "a/../../x", "/etc/passwd", "C:/Windows", "sub/../../out"):
        with pytest.raises(ff.FolderPathError):
            ff.resolve_under_root(root, bad)

def test_resolve_under_root_rejects_symlink_escape(root, outside):  # outside=tmp_path 外另一目录
    (root / "link").symlink_to(outside)
    with pytest.raises(ff.FolderPathError):
        ff.resolve_under_root(root, "link/secret.txt")

def test_read_text_gbk_fallback(tmp_path):
    p = tmp_path / "gbk.txt"; p.write_bytes("中文注释".encode("gbk"))
    assert "中文注释" in ff.read_text_bounded(p)
```

```python
# tests/agent/test_folder_tools.py 追加（ctx/db 夹具同任务 1；目录夹具同上）
def test_list_folder_files_paginates(db, repo):       # 造 3 个文件 → page_size 内 1 页，断言 entries/rel_path/is_dir/size
    ...
def test_read_folder_file_lines_and_next_call(db, repo):
    out = read_folder_file(db, folder="repo", path="a.py", start_line=1, max_lines=2, ctx=ctx7(repo))
    assert '"start_line": 1' in out and '"next_call"' in out and '"total_lines"' in out
def test_read_folder_file_rejects_binary_and_oversize(db, repo):   # big.bin → error 含"二进制"；3MB 文本 → error 含大小
    ...
def test_read_folder_file_gbk(db, repo):              # gbk.txt 读取含 "中文注释"
    ...
def test_read_folder_file_doc_via_parse_file_no_sidecar(db, tmp_path):
    # 造一个最小 docx（或用现有测试资产）；断言返回含正文文本，且 tmp_path 树内没有新增 .md 文件
    ...
def test_folder_gone_clear_error(db, tmp_path):
    # 附加一个已删除路径的 folder 行 → 两个工具都返回 ok:false 且提示让用户移除 chip
    ...
def test_resolve_folder_ambiguous_lists_candidates(db):   # 两个 label 同为 "repo" → error 同时含两个 root_path
    ...
```

- [ ] **步骤 2：运行验证失败**：两个测试文件 → FAIL（folder_files 不存在）
- [ ] **步骤 3：实现**
  - `domain/folder_files.py`：
    - 常量三张清单照规格 §10 逐字：`IGNORED_DIRS`（所有 `.` 开头目录 + `node_modules __pycache__ venv env dist build target out bin obj coverage .next .nuxt .pytest_cache .mypy_cache .ruff_cache .turbo .parcel-cache`）、`INDEX_TEXT_EXTS` + `NO_EXT_TEXT_NAMES`（白名单）、`BINARY_EXTS`（读取黑名单）；`READ_DOC_EXTS = {'.pdf', '.docx', '.pptx', '.xlsx', '.csv'}`；`LIST_PAGE_SIZE=500`、`READ_MAX_BYTES=2*1024*1024`、`MAX_LINES_DEFAULT=200`、`MAX_LINES_LIMIT=500`
    - `class FolderPathError(ValueError)`；`resolve_under_root(root: Path, rel: str) -> Path`：rel 含 `..` 段/以 `/` `\` 或盘符开头、或 `Path.resolve()` 后 `not is_relative_to(root.resolve())` → raise FolderPathError("只允许附加根内的相对路径")
    - `walk(root: Path) -> Iterator[tuple[str, Path, int, float]]`：os.scandir 递归产出 `(rel_path, path, size, mtime)`，忽略规则过滤，rel_path 用 `/` 分隔（供索引/直扫/列目录复用）
    - `list_entries(root: Path, subdir: str, page: int) -> dict`：基于 walk 的目录视图——文件与**未忽略的目录**都出条目（`{name, rel_path, is_dir, size}`，目录 size=0），subdir 过滤后按 rel_path 排序切页（500/页），返回 `{entries, page, next_page}`
    - `read_text_bounded(path: Path) -> str`：>2MB 拒绝；`utf-8-sig` → 失败换 `gbk` → 仍失败 `utf-8 errors='replace'`
    - `read_doc_markdown(path: Path) -> str`：`parse_file(path).markdown`（禁止 ensure_parsed/sidecar）；kind 为 `unsupported`/空 markdown 时返回带说明的错误文本
  - `folder_tools.py`：
    - `_resolve_folder(db, ctx, folder: str)`：当前会话附加行中 label 精确等于 → 唯一命中；否则 root_path 子串匹配，0 命中/多命中 → 候选清单错误 JSON；附带检查 `Path(root_path).is_dir()`，不存在 → "文件夹已不存在，可让用户在输入区移除该附件"
    - `list_folder_files(db: Session, folder: str, subdir: str = "", page: int = 1, ctx=None) -> str`：docstring 一句话；调 `folder_files.resolve_under_root` + `folder_files.list_entries`（含目录条目）；root 消失走 `_resolve_folder` 错误
    - `read_folder_file(db: Session, folder: str, path: str, start_line: int = 1, max_lines: int = 200, ctx=None) -> str`：`max_lines` 钳到 ≤500；BINARY_EXTS → 二进制错误；READ_DOC_EXTS → `read_doc_markdown` 全文返回（附 next_call 说明按行翻页）；否则 `read_text_bounded` 按 `splitlines()` 切页，返回 `{ok, rel_path, start_line, end_line, total_lines, content, next_call}`，`next_call` 给下一页参数
    - 注册两个 ToolSpec（readonly, FOLDER_FLAG），并入 `_FOLDER_SPECS` 与 `FOLDER_TOOLS`
- [ ] **步骤 4：运行验证通过**：两个测试文件 + 任务 1 测试回归 → PASS
- [ ] **步骤 5：Commit**，信息：`feat: folder file listing and reading tools`

### 任务 3：每轮注入【对话文件夹】块

**文件：**
- 修改：`backend-v2/src/zhishi/agent/tools/folder_tools.py`（加 `folder_context_block`）
- 修改：`backend-v2/src/zhishi/agent/runtime.py:523-528`（研究项目块之后追加）
- 测试：`backend-v2/tests/agent/test_folder_injection.py`

- [ ] **步骤 1：编写失败的测试**

```python
"""注入纪律：零附加零注入；有附加注入单块（label/路径/工具名齐全）。"""
def test_block_empty_when_no_folders(db):
    assert folder_context_block(db, conversation_id=7) == ""
def test_block_lists_folders_with_tool_names(db):
    # 附加两行 → 块内含 "【对话文件夹】"、"list_folder_files"、"read_folder_file"、
    # "search_folder_files"、两个 label 与两个 root_path
    ...
```

- [ ] **步骤 2：运行验证失败** → FAIL（folder_context_block 不存在）
- [ ] **步骤 3：实现**
  - `folder_tools.py` 加 `folder_context_block(db: Session, conversation_id: int | None) -> str`：conversation_id 为 None 或无附加行返回 `""`；有则返回规格 §8 原文文案（头两行固定 + 每个 folder 一行 `- {label} → {root_path}`）
  - `runtime.py` 在研究项目块 if 之后追加：
    ```python
    from zhishi.agent.tools.folder_tools import folder_context_block
    folder_block = folder_context_block(db, conversation_id)
    if folder_block:
        full_user += '\n\n' + folder_block
    ```
- [ ] **步骤 4：运行验证通过**（新文件 + `tests/agent/test_memory_tools.py` 注入回归 + `tests/agent/test_prompt_cache_replay.py` 守卫）→ PASS
- [ ] **步骤 5：Commit**，信息：`feat: inject attached folders context into runs`

### 任务 4：REST 三端点

**文件：**
- 创建：`backend-v2/src/zhishi/server/routes/conversation_folders.py`
- 修改：`backend-v2/src/zhishi/server/app.py:217-222`（import 与 include_router 两个元组各加 `conversation_folders`）
- 测试：`backend-v2/tests/server/test_conversation_folders_api.py`

- [ ] **步骤 1：编写失败的测试**（夹具照 test_memories_api.py：`with TestClient(create_app(data_dir=tmp_path))`；先用 POST `/ai/chat` 建会话或直接向 `ai_conversations` 插行取 id——用 TestClient 内部 app.state.session_factory 插行最简单）

```python
def test_folders_crud(tmp_path):
    # GET 空列表 []；POST 真实临时目录 → 201 返回 label=目录名；重复 POST 同路径 → 409；
    # POST 不存在路径 → 400；POST 文件路径(非目录) → 400；GET 列表含该行；
    # DELETE → 204 且再 GET 为空；DELETE 不存在 id → 404
def test_delete_purges_chunks(tmp_path):
    # 附加后手工插入 folder_file_chunks 行 → DELETE → 断言 chunk 表无该 folder_id 的行
def test_unknown_conversation_404(tmp_path): ...
```

- [ ] **步骤 2：运行验证失败** → FAIL（404 路由不存在）
- [ ] **步骤 3：实现**（照 routes/memories.py 模式）
  - `router = APIRouter(prefix="/ai/conversations/{conversation_id}/folders", tags=["conversation-folders"])`
  - `FolderOut(id, label, root_path, created_at)`、`FolderCreate(root_path: str)`；GET `""` → list[FolderOut]（404 会话不存在）；POST `""`：`Path(root_path)` 须存在且 `is_dir()`（否则 400），同会话同 `root_path`（字符串相等）重复 409，label=路径最后一段名，201 返回；DELETE `/{folder_id}`：404 校验归属本会话，先 `delete(FolderFileChunk).where(folder_id==…)` 再删 folder 行，204
  - app.py 两个元组加 `conversation_folders`
- [ ] **步骤 4：运行验证通过** → PASS
- [ ] **步骤 5：Commit**，信息：`feat: REST endpoints for conversation folder attachment`

### 任务 5：惰性索引 + `search_folder_files` + 启动 GC

**文件：**
- 修改：`backend-v2/src/zhishi/domain/folder_files.py`（索引/对账/直扫/清理）
- 修改：`backend-v2/src/zhishi/agent/tools/folder_tools.py`（search 工具）
- 修改：`backend-v2/src/zhishi/server/app.py`（lifespan 内 OCR resume 之后加 GC 调用）
- 测试：`backend-v2/tests/domain/test_folder_files.py`（追加）、`backend-v2/tests/agent/test_folder_tools.py`（追加）

- [ ] **步骤 1：编写失败的测试**

```python
# tests/domain/test_folder_files.py 追加
def test_search_fresh_after_edit(db, repo):        # 建索引→改文件→再搜命中新内容（mtime 对账）
def test_search_drops_deleted(db, repo):           # 删文件→再搜不再命中
def test_first_build_overflow_degrades_to_scan(db, big_repo):  # >2000 文件（循环造空文件）→ index_overflow 置位、mode=scan、仍出结果
def test_reconcile_giveup_scans(db, repo):         # 一次改 >500 个文件 → 本次 mode=scan 不炸
def test_purge_and_gc(db, repo):                   # purge_folder 清块；gc_orphans 清 folder 无主块（造孤儿行）
```

```python
# tests/agent/test_folder_tools.py 追加
def test_search_folder_files_returns_line_matches(db, repo):   # 命中含 rel_path/line_no/snippet，上限 50 truncated
def test_search_folder_files_requires_keyword(db, repo):       # 空 keyword → ok:false 教学
```

- [ ] **步骤 2：运行验证失败** → FAIL（search 函数不存在）
- [ ] **步骤 3：实现**
  - `folder_files.py` 加：`CHUNK_LINES=150`、`INDEX_BUILD_FILE_LIMIT=2000`、`RECONCILE_CHANGE_LIMIT=500`、`INDEX_MAX_FILE_BYTES=512*1024`、`SEARCH_MATCH_LIMIT=50`
  - `search_files(db: Session, folder_row, keyword: str) -> dict`（唯一入口，返回 `{ok, matches:[{rel_path, line_no, snippet}], total, truncated, mode:'index'|'scan'}`）：`folder_row.index_overflow` 或首建/对账失败 → 直扫；否则 `ensure_index`（walk 快照 vs 索引按 rel_path 聚合的 mtime/size 对账：新增/变更重分块、消失删行；变更数 >RECONCILE_CHANGE_LIMIT → 放弃增量返回 False；首建文件数 >INDEX_BUILD_FILE_LIMIT → 置 `index_overflow=True` 落库并直扫）后查 chunk 命中；直扫=walk + `read_text_bounded` 逐文件找关键词；两种路径同受 512KB/50 命中上限
  - `purge_folder(db, folder_id)`、`gc_orphans(session_factory) -> int`（删 folder_id 不在 ai_conversation_folders 的 chunk 行）
  - `folder_tools.py`：`search_folder_files(db: Session, folder: str, keyword: str, ctx=None) -> str`，docstring 一句话；空 keyword 教学错误；调 `search_files`
  - app.py lifespan（resume_pending 之后）：`from zhishi.domain import folder_files as folder_files_mod` + `folder_files_mod.gc_orphans(app.state.session_factory)`，有清理量则 log.info
  - 任务 4 的 DELETE 已显式清 chunk——本任务的 purge 供其复用（把任务 4 内联删除改为调 `purge_folder`，保持单一实现）
- [ ] **步骤 4：运行验证通过**（两个测试文件 + `tests/server/test_conversation_folders_api.py` 回归；此时四个工具全部注册，追加最终门控断言 `FOLDER_TOOLS <= {s.name for s in specs_for(db)}`）→ PASS
- [ ] **步骤 5：Commit**，信息：`feat: lazy keyword index cache for folder search`

### 任务 6：Electron 目录选择 IPC

**文件：**
- 修改：`electron-v2/desktop-settings.js`（createDesktopSettings 内加 handler + dispose 注销）
- 修改：`electron-v2/main-preload.js`（zhishiDesktop 桥加 selectDirectory）

- [ ] **步骤 1：实现 handler**
  - desktop-settings.js：`ipcMain.handle('desktop:select-directory', event => { guard(event); const win = getMainWindow(); ... dialog.showOpenDialog(win, { properties: ['openDirectory'] }) ... })`，顶部 `const { dialog } = require('electron')`；返回选中数组首项字符串或 `null`（取消/窗口销毁）；dispose 里 `ipcMain.removeHandler('desktop:select-directory')`
  - main-preload.js：`selectDirectory: () => ipcRenderer.invoke('desktop:select-directory')`
- [ ] **步骤 2：静态校验**：`cd /e/知时-v2/electron-v2 && node --check desktop-settings.js && node --check main-preload.js` → 无输出即通过（Electron 主进程无单测设施，行为由任务 8 手工验收覆盖）
- [ ] **步骤 3：Commit**，信息：`feat: electron directory picker IPC`

### 任务 7：前端——API 层 / store / 输入区按钮与 chip

**文件：**
- 创建：`frontend-v2/app/src/api/conversationFolders.ts`
- 修改：`frontend-v2/app/src/stores/conversation.ts`（state + 3 个 action + select 接线）
- 修改：`frontend-v2/app/src/components/AppIcon.vue`（IconName 加 `'folder'` + PATHS 加路径串）
- 修改：`frontend-v2/app/src/components/chat/ChatInput.vue`（按钮 + chips）
- 测试：创建 `frontend-v2/app/src/stores/conversation-folders.test.ts`；修改 `frontend-v2/app/src/components/chat/ChatInput.test.ts`（追加）

- [ ] **步骤 1：编写失败的 store 测试**（node 环境，vi.mock api 模块）

```typescript
// stores/conversation-folders.test.ts：mock ../api/conversationFolders 后
// loadFolders：activeId=7 → folders 置为返回值；activeId=null → 置空
// attachFolder('E:/x') → api 以 (7,'E:/x') 调用、行入 folders；api 抛错 → error 置位
// detachFolder(3) → api 调用且行移除
```

- [ ] **步骤 2：运行验证失败**：`npx vitest run src/stores/conversation-folders.test.ts` → FAIL（api 模块不存在）
- [ ] **步骤 3：实现 api + store**
  - `api/conversationFolders.ts` 照 memories.ts 手写类型头注释（含"rest.d.ts 红线：不重生成"）：`ConversationFolder { id; label; root_path; created_at }` + `listFolders(cid)` / `attachFolder(cid, rootPath)` / `detachFolder(cid, id)`（http.get/post/del）
  - `stores/conversation.ts`：state 加 `folders: [] as ConversationFolder[]`；`select(id)` 里在 `this.messages = messages` 之后加带 viewVersion 守卫的 `this.folders = await listFolders(id)`；`async loadFolders()`、`async attachFolder(rootPath: string)`（viewVersion 守卫 + error 路径，照 uploadAttachment 风格）、`async detachFolder(id: number)`
- [ ] **步骤 4：运行验证通过** → PASS
- [ ] **步骤 5：编写失败的 ChatInput UI 测试**（追加进现有 Playwright 夹具：fixture 的 load() 虚拟入口里按 `?bridge=1` 注入 `window.zhishiDesktop = { selectDirectory: async () => window.__picked }`；用 `page.route('**/ai/conversations/*/folders*')` 兜底 POST/DELETE/GET）
  - 无桥（不带 ?bridge=1）→ 文件夹按钮不可见
  - 有桥 + `activeId` 已设 + `__picked='E:/demo'` → 点按钮 → chip 显示 `demo`；点 chip 的 × → chip 消失
  - `activeId=null` → 按钮禁用（title 提示先发第一条消息）
- [ ] **步骤 6：实现 UI**
  - AppIcon：`IconName` 加 `'folder'`，PATHS 加一个简洁文件夹轮廓 path（描边风格与现有一致）
  - ChatInput.vue：`const hasFolderBridge = conv.surface === 'main' && !!(window as any).zhishiDesktop?.selectDirectory`（仅主窗口且桥在）；paperclip 旁加同款 `.ibtn`（`:disabled="attachmentsDisabled || conv.activeId === null"`，title="附加文件夹（知时可读取其中文件）"，无会话时 title="发送第一条消息后可附加文件夹"）；点击 `const p = await zhishiDesktop.selectDirectory(); if (p) await conv.attachFolder(p)`；chips 行（现有 `.chips` 容器内、附件 chips 之前）渲染 `conv.folders`：`.chip` 样式 + `<AppIcon name="folder" :size="11"/>` + label + `×` 按钮（disabled 同附件，调 `conv.detachFolder`）
- [ ] **步骤 7：运行验证通过**：ChatInput 全文件（旧用例不回归）+ store 测试 + `npm run build`（vue-tsc 过）→ PASS
- [ ] **步骤 8：Commit**，信息：`feat: attach folder UI in chat input`

### 任务 8：全量回归 + 手工验收

**文件：** 无新改动（发现问题回对应任务修复后重跑）

- [ ] **步骤 1：后端全量**：`cd /e/知时-v2/backend-v2 && .venv/Scripts/python.exe -m pytest tests`（约 3-4 分钟）→ 全绿；特别确认 `tests/agent/test_prompt_cache_replay.py`（工具数==6）与 `tests/agent/test_tool_usability.py`（8192 小窗）不动全绿
- [ ] **步骤 2：前端全量**：`cd /e/知时-v2/frontend-v2/app && npx vitest run && npm run build` → 全绿
- [ ] **步骤 3：手工验收**（开发态起后端+前端+Electron，对照规格 §1 成功标准 1-5）：附加真实代码仓库 → chip 出现；问"我们项目用的什么框架"；改一个文件再问（读到新内容）；移除 chip 后再问（工具报无附加）；未附加的新会话正常聊天（无注入痕迹）
- [ ] **步骤 4：如有修复**，按全局约束流程提交：`test: folder attachment regression fixes`；无修复则本任务零提交
