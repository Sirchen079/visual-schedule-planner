# 对话文件夹附件（Conversation Folder Attachment）设计规格

- 日期：2026-09-29
- 状态：设计已获用户批准，待写实现计划
- 路径：架构级新功能（新表、新工具、Electron IPC、前端 UI）

## 1. 背景与目标

用户希望"把我们的代码给知时看"：在对话过程中把电脑上的一个文件夹（如代码仓库）附加进对话，知时被问到时能列出、读取、搜索其中的文件，从而了解用户当前的技术路线与代码现状。

核心体验（用户已确认）：

- **按需查阅**：不做背景画像/摘要注入，知时只在被问到时读文件；读取永远实时，读到的一定是磁盘当前内容。
- **对话级附加**：像添加附件一样在输入区附加文件夹，随会话持久化；不建"项目"实体，没有设置页管理界面。
- **搜索加速缓存**（用户选定的方案三）：首次搜索时惰性建索引，之后 mtime 对账增量维护；缓存只加速搜索，读取永不走缓存。

成功标准：

1. 对话中点文件夹按钮 → 系统目录选择框 → 附加成功，chip 出现在附件行；
2. 问"我们项目用的什么框架/某功能在哪个文件"，知时通过工具给出基于实际文件内容的回答；
3. 代码文件改动后，紧接着再问，读到的是新内容；
4. 移除 chip 后知时不再能读取该文件夹；
5. 未附加文件夹的对话，线上请求与现状完全一致（零注入、工具数守卫不变）。

## 2. 非目标

- 持久"项目"实体、跨会话项目库（重新附加即可，成本低）
- 写入/修改/删除文件夹内文件（工具全部只读）
- 语义/向量检索（关键词字面匹配，与既有 reading.search 同级）
- 解析 .gitignore（内置忽略清单覆盖大头，列为后续）
- 后台文件 watcher / 变更通知
- 纯浏览器环境的文件夹选择（Electron IPC 专属；非 Electron 环境按钮隐藏）
- OCR（扫描版 PDF 返回已有文本层并提示，不进 OCR 管道）

## 3. 总体架构

```
输入区文件夹按钮 ──Electron IPC(目录选择)──▶ 前端 store
        │                                        │ POST/DELETE /ai/conversations/{cid}/folders
        ▼                                        ▼
   chip 显示/移除                        ai_conversation_folders 表
                                                 │
   每轮 run 注入一行【对话文件夹】块 ◀── runtime.run_stream（研究项目块之后）
                                                 │
   list_folders / list_folder_files / read_folder_file / search_folder_files
   （readonly 工具，search_tools 发现，execute_tool 派发）
        │                        │
        ▼                        ▼
   直读磁盘（读/列）      惰性索引缓存 folder_file_chunks（仅搜索用）
```

## 4. 数据模型（`backend-v2/src/zhishi/domain/models.py`）

新表两张，随 `create_all` 幂等建表（`server/app.py:20-53` 现有机制，无需补列 patch）：

```python
class AIConversationFolder(Base):
    __tablename__ = "ai_conversation_folders"
    id: int PK
    conversation_id: int          # 所属 ai_conversations.id
    root_path: str                # 绝对路径原样字符串
    label: str                    # 默认取文件夹名（v1 不提供改名）
    index_overflow: bool = False  # 首建超 2000 文件上限后置位：该文件夹搜索永久直扫
    created_at: datetime

class FolderFileChunk(Base):
    __tablename__ = "folder_file_chunks"
    id: int PK
    folder_id: int                # AIConversationFolder.id
    rel_path: str                 # 相对根的路径，正斜杠分隔
    mtime: float                  # 索引时文件 mtime（冗余存于每行，按 rel_path 聚合对账）
    size: int
    line_start: int               # 该块覆盖的行号范围（1 起始，闭区间）
    line_end: int
    content: str
```

- 不依赖 FK 级联（SQLite 需 PRAGMA 才强制）：DELETE 端点显式先删 chunks 再删 folder 行。
- 启动 GC（`server/app.py` 启动钩子内，`resume_pending` 旁）：清理 folder_id 无主的孤儿 chunk 行。

## 5. REST API（新 `server/routes/conversation_folders.py`，`app.py` include_router 登记）

| 方法 | 路径 | 行为 |
|---|---|---|
| GET | `/ai/conversations/{cid}/folders` | 列表 `[{id, label, root_path, created_at}]` |
| POST | `/ai/conversations/{cid}/folders` | body `{root_path}`；校验：路径存在、是目录、同会话未重复（重复 409）；成功 201 返回实体（label 服务端取文件夹名） |
| DELETE | `/ai/conversations/{cid}/folders/{fid}` | 204；显式删 chunk 行 + folder 行 |

前端 `api/conversationFolders.ts` **手写类型**（红线：不重生成 rest.d.ts，照 `api/memories.ts` 模式）。

## 6. Electron 目录选择

- `electron-v2/main.js`：`ipcMain.handle('desktop:select-directory')` → `dialog.showOpenDialog(win, { properties: ['openDirectory'] })` → 返回选中路径字符串或 `null`（取消）。
- `electron-v2/main-preload.js`：`zhishiDesktop` 桥新增 `selectDirectory: () => ipcRenderer.invoke('desktop:select-directory')`。
- 前端通过 `window.zhishiDesktop?.selectDirectory` 调用；桥不存在（非 Electron）时文件夹按钮 `v-if` 隐藏。

## 7. 前端（`frontend-v2/app/src`）

- **按钮**：`components/chat/ChatInput.vue` 工具行，paperclip 旁新增同款 28px 图标按钮（`AppIcon` 补 `folder` 图标）；title="附加文件夹（知时可读取其中文件）"；run 活跃/上传中与附件按钮同等禁用。
- **chip**：附加后显示在现有 chips 行（`.chip` 样式复用 + folder 小图标 + label + `×` 移除即调 DELETE）；多个文件夹多个 chip。
- **store**：扩展 `stores/conversation.ts`——`folders: ConversationFolder[]`，切换会话时随状态拉取，`attachFolder`/`detachFolder` 动作；附加成功即生效（无需随消息发送，后端按 conversation_id 取）。
- **测试**：ChatInput 按钮与 chip 行为（`// @vitest-environment jsdom`）、store 动作，照 `ChatInput.test.ts` / `MemorySettings.test.ts` 模式。

## 8. 代理感知（注入点：`agent/runtime.py` run_stream，研究项目块之后）

仅当该会话存在 folder 行时，在当轮用户消息末尾追加：

```
【对话文件夹】用户为本对话附加了以下本地文件夹。用户说"这个项目/我们的代码"时指这些。
需要时用 list_folder_files 列文件、read_folder_file 读文件、search_folder_files 搜索。
- {label} → {root_path}
```

- 零文件夹零注入（与记忆块同一纪律，见 `prompts.py:192-195` 注释；8192 小窗测试库天然无文件夹保持全绿）。
- 不加任何常驻 instructions；工具教学放在 docstring 与校验消息（"校验即教学"，照 `memory_tools.py` 模式）。

## 9. 代理工具（新 `agent/tools/folder_tools.py`，全部 `safety='readonly'`，`feature_flag='feature_folder_tools_enabled'` 加入 `settingsvc.DEFAULTS` 默认 `"true"`）

注册走 `ToolSpec + register()`，`tools/__init__.py` 加一行 import；不进 CORE_TOOLS，靠 search_tools 发现。参数里 `folder` 一律按 label 或 root_path 前缀/子串匹配解析到唯一附加根，歧义时报出候选清单。

### 9.1 `list_folders()`
返回当前对话附加的文件夹 `[{label, root_path}]`；无附加时返回提示（教模型先让用户附加）。

### 9.2 `list_folder_files(folder, subdir="", page=1)`
- 按忽略规则（§10）walk，返回 `{entries: [{name, rel_path, is_dir, size}], page, next_page}`；每页 500 条，超出提示翻页。
- `subdir` 必须是相对路径（含 `..`、绝对路径形态即拒绝）。

### 9.3 `read_folder_file(folder, path, start_line=1, max_lines=200)`
- **永远实时读磁盘，不经索引**；`path` 相对根，绝对/`..` 拒绝。
- 行号分页：返回 `{rel_path, start_line, end_line, total_lines, content, next_call}`（`next_call` 给出下一页参数，照 read_material 纪律）；`max_lines` 上限 500。
- 单文件硬上限 2MB（超出拒绝并报大小）；二进制后缀（§10 黑名单）拒绝并说明。
- 编码：UTF-8 → GBK → UTF-8(`errors='replace'`) 三级回退。
- 文档后缀（.pdf/.docx/.pptx/.xlsx/.csv）走 `adapters/parsers.py: parse_file()` **内存解析取 markdown 文本，禁止调用 ensure_parsed（不写 sidecar，不在用户文件夹里落任何文件）**；扫描版 PDF 文本层为空时明确提示。

### 9.4 `search_folder_files(folder, keyword)`
- 返回 `{matches: [{rel_path, line_no, snippet}], total, truncated}`，上限 50 条命中，超出置 `truncated` 并建议换更具体关键词。
- 加速路径：有索引且对账通过 → 查 `folder_file_chunks`；否则直扫（§11）。

## 10. 忽略规则（`folder_tools.py` 常量，大小写不敏感）

- **目录**：所有以 `.` 开头的目录（覆盖 .git/.venv/.idea 等）＋ 非点清单：`node_modules __pycache__ venv env dist build target out bin obj coverage .next .nuxt .pytest_cache .mypy_cache .ruff_cache .turbo .parcel-cache`。
- **索引白名单**（仅这些后缀进索引/直扫；无后缀的常见文本文件名另列入白名单：`Dockerfile Makefile LICENSE README CHANGELOG .gitignore .env*` 等）：`py ts tsx js jsx mjs cjs vue svelte java c cc cpp cxx h hh hpp cs go rs rb php swift kt kts scala sh bash zsh ps1 bat cmd md markdown txt log json yaml yml toml ini cfg conf xml html htm css scss less sql r m`。
- **读取黑名单**（read/list 可见但 read 拒绝）：`png jpg jpeg gif webp bmp ico tiff exe dll so dylib bin dat zip 7z rar tar gz bz2 xz jar class pyc pyd woff woff2 ttf otf mp3 mp4 avi mov sqlite db` 等二进制/媒体/压缩/字体类型。
- **大小**：索引/直扫跳过 >512KB 的文本文件；read 硬上限 2MB。

## 11. 搜索索引缓存（惰性 + 增量）

- **建**：`search_folder_files` 首次调用时在该文件夹上建（在工具调用线程内同步执行）：walk → 白名单文本文件 → 按 150 行/块切 `folder_file_chunks`。首建工作量上限 **2000 个文件**，超限置 `ai_conversation_folders.index_overflow`，该文件夹此后搜索永久直扫。
- **对账**：每次搜索先 walk 取 `(rel_path, mtime, size)` 快照，与索引按 `rel_path` 聚合对比：新增/变更文件即时重分块，消失的删行；变更文件数 >500 时放弃本次增量、整轮直扫并记 log。
- **直扫**：walk 时对白名单文件逐个读入找关键词（同样受 512KB/文件 与 50 命中上限约束）。
- **清理**：detach 端点显式删；启动 GC 孤儿行。会话删除后 folder 行残留不产生任何读权限（工具只认"当前 run 的 conversation_id"）。
- **新鲜度纪律**：缓存只加速搜索且必须先对账再出结果——缓存可以慢，不能说谎。

## 12. 路径安全（授权模型 = 附加动作本身）

- 工具侧 root 一律从 DB 读，不信任请求参数里的 root。
- 目标路径 `Path.resolve()` 后必须 `is_relative_to(root.resolve())`；symlink 解析后同规则（防符号链接逃逸）。
- `path`/`subdir` 参数只接受相对路径：含 `..` 段、以 `/` `\` 或盘符开头即拒绝。
- 读取仅限 readonly 工具，无任何写路径触碰外部文件夹。

## 13. 错误处理（工具返回结构化 `{error}` 文本，模型可自救重试）

| 场景 | 行为 |
|---|---|
| 文件夹参数无法解析/歧义 | 报候选 label+路径清单 |
| 磁盘上文件夹已删除 | 明确提示"文件夹已不存在，可让用户在输入区移除" |
| 越权路径（../、绝对路径、symlink 逃逸） | 拒绝并说明只读根内相对路径 |
| 二进制/超大文件 | 拒绝并报类型/大小 |
| 编码无法判定 | 第三级 `errors='replace'` 兜底，不抛异常 |
| OS 权限拒绝（如系统目录） | 透传清晰错误 |

## 14. 预算与守卫红线（不可破）

1. 新工具**不进 CORE_TOOLS**；新增守卫断言（照 `tests/agent/test_memory_tools.py:145-147` 模式：`assert not FOLDER_TOOLS & CORE_TOOLS`）。
2. `tests/agent/test_prompt_cache_replay.py:183` 的 `== 6` 与 `test_tool_usability.py:33` 的 8192 小窗测试必须全绿不动（零常驻 instructions、零文件夹零注入保证）。
3. 工具 docstring 保持克制短句（线上成本守卫惯例）。
4. `rest.d.ts` 不重生成，前端手写类型。

## 15. 测试计划

**后端**
- `tests/agent/test_folder_tools.py`：四工具语义；分页/next_call；GBK 样本回退；二进制/超大拒绝；越权（`../`、绝对路径、symlink 逃逸）；忽略规则生效；零文件夹错误消息；守卫断言不进 CORE_TOOLS。
- `tests/agent/test_folder_injection.py`：无文件夹零注入（一个字符不加）；有文件夹注入单块（照记忆注入测试模式）。
- `tests/domain/test_folder_index.py`：首建；增量（改文件→新内容命中、删文件→不再命中）；overflow 降级直扫；对账放弃路径；清理。
- `tests/server/test_conversation_folders_api.py`：CRUD/重复 409/路径校验/删除级联清 chunk。
- parse_file 内存解析回归：断言读取 PDF/docx 后用户目录内**没有**生成 sidecar `.md`。

**前端**
- ChatInput：按钮（非 Electron 隐藏）/chip 渲染与移除/禁用态（jsdom 注解）。
- conversation store：folders 拉取、attach/detach 动作。
- `api/conversationFolders.ts` 类型冒烟。

**守卫回归**：`test_prompt_cache_replay`、`test_tool_usability` 全量跑绿。

## 16. 实现切片建议（供实现计划参考）

1. **后端域层**：models 两表 + folder_tools 四工具（先直读直扫，无索引）+ 注入块 + 守卫断言 + 测试。
2. **REST + 索引缓存**：路由三端点 + 惰性索引/对账/overflow + 启动 GC + 测试。
3. **Electron + 前端**：select-directory IPC/preload + 按钮/chip/store/api + 测试。
4. **收尾**：全量 pytest + vitest + vue-tsc 构建绿；手工验收（真实仓库文件夹走一遍成功标准 1-5）。
