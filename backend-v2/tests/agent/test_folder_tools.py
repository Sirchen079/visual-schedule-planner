"""对话文件夹工具：list_folders 语义、registry 开关门控、CORE_TOOLS 守卫；
list_folder_files / read_folder_file 的分页、行号 next_call、二进制/超大拒绝、GBK、文档内存解析。"""
import json
import shutil

import pytest

from zhishi.agent.tools.folder_tools import (FOLDER_FLAG, FOLDER_TOOLS, list_folder_files,
                                             list_folders, read_folder_file)
from zhishi.agent.tools.registry import specs_for
from zhishi.agent.tool_discovery import CORE_TOOLS
from zhishi.domain import settingsvc
from zhishi.domain.models import AIConversation, AIConversationFolder
from zhishi.infra.database import make_engine, make_session_factory, create_all


@pytest.fixture
def db(tmp_path):
    engine = make_engine(tmp_path / "test.db")
    create_all(engine)
    session = make_session_factory(engine)()
    yield session
    session.close()
    engine.dispose()


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


# ---- list_folder_files / read_folder_file（任务 2）----

@pytest.fixture
def repo(tmp_path):
    """repo/ 夹具：与域层测试同构（文本、忽略目录、3MB 二进制、GBK 中文）。"""
    base = tmp_path / "repo"
    (base / "docs").mkdir(parents=True)
    (base / "sub").mkdir()
    (base / "node_modules").mkdir()
    (base / ".git").mkdir()
    (base / "a.py").write_text("x = 1\ny = 2\nz = 3\nprint(x + y + z)\n", encoding="utf-8")
    (base / "docs" / "readme.md").write_text("# readme\n", encoding="utf-8")
    (base / "sub" / "inner.ts").write_text("export const y = 2;\n", encoding="utf-8")
    (base / "node_modules" / "junk.js").write_text("var junk = 3;\n", encoding="utf-8")
    (base / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    (base / "big.bin").write_bytes(b"\0" * (3 * 1024 * 1024))
    (base / "gbk.txt").write_bytes("中文注释".encode("gbk"))
    return base


@pytest.fixture
def ctx7(db):
    """造会话 + 附加目录（label 固定 repo）并返回指向它的 ctx。"""
    def make(root):
        conv = AIConversation(title="t")
        db.add(conv)
        db.commit()
        db.refresh(conv)
        db.add(AIConversationFolder(conversation_id=conv.id, root_path=str(root), label="repo"))
        db.commit()
        return type("C", (), {"deps": type("D", (), {"conversation_id": conv.id})})()
    return make


def test_list_folder_files_paginates(db, tmp_path, ctx7):
    root = tmp_path / "repo"
    (root / "sub").mkdir(parents=True)
    (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    (root / "b.py").write_text("y = 2\n", encoding="utf-8")
    (root / "sub" / "c.txt").write_bytes(b"hello\n")
    out = list_folder_files(db, folder="repo", ctx=ctx7(root))   # type: ignore[arg-type]
    data = json.loads(out)
    assert data["ok"] is True and data["page"] == 1 and data["next_page"] is None   # 3 文件 1 页内
    by_rel = {e["rel_path"]: e for e in data["entries"]}
    assert set(by_rel) == {"a.py", "b.py", "sub", "sub/c.txt"}
    assert by_rel["sub"]["is_dir"] is True and by_rel["sub"]["size"] == 0
    assert by_rel["sub/c.txt"]["is_dir"] is False and by_rel["sub/c.txt"]["size"] == len("hello\n")
    assert by_rel["a.py"]["name"] == "a.py"


def test_list_folder_files_rejects_escape_subdir(db, repo, ctx7):
    out = list_folder_files(db, folder="repo", subdir="../outside", ctx=ctx7(repo))   # type: ignore[arg-type]
    assert '"ok": false' in out and "相对路径" in out


def test_read_folder_file_lines_and_next_call(db, repo, ctx7):
    out = read_folder_file(db, folder="repo", path="a.py", start_line=1, max_lines=2,
                           ctx=ctx7(repo))   # type: ignore[arg-type]
    assert '"start_line": 1' in out and '"next_call"' in out and '"total_lines"' in out
    data = json.loads(out)
    assert data["end_line"] == 2 and data["total_lines"] == 4
    assert data["next_call"]["args"]["start_line"] == 3
    tail = read_folder_file(db, **{"folder": "repo", "path": "a.py", "start_line": 3, "max_lines": 2,
                                   "ctx": ctx7(repo)})   # type: ignore[arg-type]
    assert json.loads(tail)["next_call"] is None


def test_read_folder_file_rejects_binary_and_oversize(db, repo, ctx7):
    ctx = ctx7(repo)
    out = read_folder_file(db, folder="repo", path="big.bin", ctx=ctx)   # type: ignore[arg-type]
    assert '"ok": false' in out and "二进制" in out
    (repo / "huge.txt").write_text("好" * (1024 * 1024), encoding="utf-8")   # 3MB 纯文本
    out = read_folder_file(db, folder="repo", path="huge.txt", ctx=ctx)   # type: ignore[arg-type]
    assert '"ok": false' in out and "3.0MB" in out and "2MB" in out


def test_read_folder_file_rejects_escape_path(db, repo, ctx7):
    out = read_folder_file(db, folder="repo", path="../outside/secret.txt", ctx=ctx7(repo))   # type: ignore[arg-type]
    assert '"ok": false' in out and "相对路径" in out


def test_read_folder_file_gbk(db, repo, ctx7):
    out = read_folder_file(db, folder="repo", path="gbk.txt", ctx=ctx7(repo))   # type: ignore[arg-type]
    assert "中文注释" in out


def test_read_folder_file_doc_via_parse_file_no_sidecar(db, tmp_path, ctx7):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "data.csv").write_text("名称,数量\n苹果,3\n香蕉,5\n", encoding="utf-8")
    before = {p for p in tmp_path.rglob("*")}
    out = read_folder_file(db, folder="repo", path="data.csv", ctx=ctx7(root))   # type: ignore[arg-type]
    assert "苹果" in out and "香蕉" in out
    after = {p for p in tmp_path.rglob("*")}
    assert after == before                        # 文档解析零落盘：目录树没有任何新增文件
    assert not any(p.suffix == ".md" for p in after)


def test_folder_gone_clear_error(db, tmp_path):
    gone = tmp_path / "gone"
    gone.mkdir()
    conv = AIConversation(title="t")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    db.add(AIConversationFolder(conversation_id=conv.id, root_path=str(gone), label="gone"))
    db.commit()
    shutil.rmtree(gone)
    ctx = type("C", (), {"deps": type("D", (), {"conversation_id": conv.id})})()
    for out in (list_folder_files(db, folder="gone", ctx=ctx),          # type: ignore[arg-type]
                read_folder_file(db, folder="gone", path="a.txt", ctx=ctx)):   # type: ignore[arg-type]
        assert '"ok": false' in out and "已不存在" in out and "移除" in out


def test_resolve_folder_ambiguous_lists_candidates(db):
    conv = AIConversation(title="t")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    db.add_all([AIConversationFolder(conversation_id=conv.id, root_path="E:/alpha", label="repo"),
                AIConversationFolder(conversation_id=conv.id, root_path="E:/beta", label="repo")])
    db.commit()
    ctx = type("C", (), {"deps": type("D", (), {"conversation_id": conv.id})})()
    out = list_folder_files(db, folder="repo", ctx=ctx)   # type: ignore[arg-type]
    assert '"ok": false' in out and "E:/alpha" in out and "E:/beta" in out
