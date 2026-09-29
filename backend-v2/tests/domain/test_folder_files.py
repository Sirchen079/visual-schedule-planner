"""folder_files 域层：忽略规则 walk、越权路径防护（../、绝对路径、symlink/junction 逃逸）、
限界文本读取；以及惰性关键词索引（对账新鲜度/降级）、purge_folder 与 gc_orphans（任务 5）。"""
import sys
from pathlib import Path

import pytest
from sqlalchemy import select

from zhishi.domain import folder_files as ff
from zhishi.domain.models import AIConversationFolder, FolderFileChunk
from zhishi.infra.database import create_all, make_engine, make_session_factory


@pytest.fixture
def db(tmp_path):
    engine = make_engine(tmp_path / "test.db")
    create_all(engine)
    session = make_session_factory(engine)()
    yield session
    session.close()
    engine.dispose()


def _folder(db, root: Path) -> AIConversationFolder:
    """给 repo 根造一条附件行（无 FK 约束，conversation_id 任意）。"""
    row = AIConversationFolder(conversation_id=1, root_path=str(root), label="repo")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def root(tmp_path):
    """repo/ 夹具：文本、忽略目录、3MB 二进制、GBK 中文各一份。"""
    base = tmp_path / "repo"
    (base / "docs").mkdir(parents=True)
    (base / "sub").mkdir()
    (base / "node_modules").mkdir()
    (base / ".git").mkdir()
    (base / "a.py").write_text("x = 1\n", encoding="utf-8")
    (base / "docs" / "readme.md").write_text("# readme\n", encoding="utf-8")
    (base / "sub" / "inner.ts").write_text("export const y = 2;\n", encoding="utf-8")
    (base / "node_modules" / "junk.js").write_text("var junk = 3;\n", encoding="utf-8")
    (base / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    (base / "big.bin").write_bytes(b"\0" * (3 * 1024 * 1024))
    (base / "gbk.txt").write_bytes("中文注释".encode("gbk"))
    return base


@pytest.fixture
def outside(tmp_path):
    """附加根之外的另一目录（symlink 逃逸目标）。"""
    other = tmp_path / "outside"
    other.mkdir()
    (other / "secret.txt").write_text("secret\n", encoding="utf-8")
    return other


def test_walk_respects_ignore_rules(root):
    rels = [r for r, *_ in ff.walk(root)]
    assert "a.py" in rels and "docs/readme.md" in rels and "sub/inner.ts" in rels
    assert not any(r.startswith(("node_modules/", ".git/")) for r in rels)


def test_resolve_under_root_accepts_inner_relative(root):
    assert ff.resolve_under_root(root, "docs/readme.md") == (root / "docs" / "readme.md").resolve()


def test_resolve_under_root_rejects_escape(root):
    for bad in ("../x", "a/../../x", "/etc/passwd", "C:/Windows", "sub/../../out"):
        with pytest.raises(ff.FolderPathError):
            ff.resolve_under_root(root, bad)


def test_resolve_under_root_rejects_symlink_escape(root, outside):
    link = root / "link"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("当前环境无 symlink 创建权限")
    with pytest.raises(ff.FolderPathError):
        ff.resolve_under_root(root, "link/secret.txt")


def _junction(root: Path, outside: Path, name: str) -> None:
    """Windows 目录联接（无需特权，resolve 与 symlink 同规则）；失败交由调用方跳过。"""
    import _winapi

    _winapi.CreateJunction(str(outside), str(root / name))


def test_resolve_under_root_rejects_junction_escape(root, outside):
    if sys.platform != "win32":
        pytest.skip("目录联接仅 Windows")
    try:
        _junction(root, outside, "jlink")
    except OSError:
        pytest.skip("无法创建目录联接")
    with pytest.raises(ff.FolderPathError):
        ff.resolve_under_root(root, "jlink/secret.txt")


def test_walk_does_not_follow_out_of_root_junction(root, outside):
    if sys.platform != "win32":
        pytest.skip("目录联接仅 Windows")
    try:
        _junction(root, outside, "jlink")
    except OSError:
        pytest.skip("无法创建目录联接")
    rels = [r for r, *_ in ff.walk(root)]
    assert not any(r.startswith("jlink/") for r in rels)   # 指向根外不列出也不深入


def test_walk_terminates_on_cyclic_junction(root):
    """指向根自身的目录联接（pnpm 等真实形态）：walk 不无限递归，正常文件仍完整列出。"""
    if sys.platform != "win32":
        pytest.skip("目录联接仅 Windows")
    try:
        _junction(root, root, "self")
    except OSError:
        pytest.skip("无法创建目录联接")
    rels = [r for r, *_ in ff.walk(root)]   # 不抛 RecursionError 即通过
    assert "a.py" in rels and "docs/readme.md" in rels and "sub/inner.ts" in rels
    assert len(rels) == len(set(rels))                     # 无重复/无限条目
    assert not any(r.startswith("self/") for r in rels)    # 环形联接不产生重复子树


def test_read_text_gbk_fallback(tmp_path):
    p = tmp_path / "gbk.txt"
    p.write_bytes("中文注释".encode("gbk"))
    assert "中文注释" in ff.read_text_bounded(p)


def test_read_text_bounded_rejects_oversize(root):
    with pytest.raises(ff.FileTooLargeError) as exc:
        ff.read_text_bounded(root / "big.bin")
    assert "3.0MB" in str(exc.value) and "2MB" in str(exc.value)


# ---- 惰性关键词索引 / search_files / purge / gc（任务 5）----

@pytest.fixture
def big_repo(tmp_path):
    """>2000 个可索引文件（循环造空文件）的首建超限场景。"""
    base = tmp_path / "big_repo"
    (base / "many").mkdir(parents=True)
    for i in range(2001):
        (base / "many" / f"f{i:04d}.txt").write_text("", encoding="utf-8")
    return base


def test_search_fresh_after_edit(db, root):
    """新鲜度纪律：建索引→改文件→再搜命中新内容、旧内容不再命中（mtime/size 对账）。"""
    row = _folder(db, root)
    first = ff.search_files(db, row, "y = 2")   # 首建索引；y = 2 在 sub/inner.ts
    assert first["ok"] is True and first["mode"] == "index"
    assert any(m["rel_path"] == "sub/inner.ts" and m["line_no"] == 1
               for m in first["matches"])
    (root / "a.py").write_text("brand_new = 'fresh_marker'\n", encoding="utf-8")
    second = ff.search_files(db, row, "fresh_marker")
    assert second["ok"] is True and second["mode"] == "index"
    assert any(m["rel_path"] == "a.py" and "fresh_marker" in m["snippet"]
               for m in second["matches"])
    stale = ff.search_files(db, row, "x = 1")   # a.py 已重写：旧内容不再命中
    assert not any(m["rel_path"] == "a.py" for m in stale["matches"])


def test_search_drops_deleted(db, root):
    """新鲜度纪律：删文件→再搜不再命中（对账删行）。"""
    row = _folder(db, root)
    assert ff.search_files(db, row, "junk_value")["total"] == 0   # 首建索引（junk.js 在忽略目录内）
    (root / "a.py").unlink()
    out = ff.search_files(db, row, "x = 1")
    assert out["ok"] is True and out["mode"] == "index"
    assert out["total"] == 0 and out["matches"] == []


def test_first_build_overflow_degrades_to_scan(db, big_repo):
    """首建 >2000 文件：置 index_overflow 落库、本次直扫、仍出结果（ok）。"""
    row = _folder(db, big_repo)
    out = ff.search_files(db, row, "anything")
    assert out["ok"] is True and out["mode"] == "scan"
    db.refresh(row)
    assert row.index_overflow is True
    again = ff.search_files(db, row, "anything")   # 永久直扫：溢出后不再尝试建索引
    assert again["ok"] is True and again["mode"] == "scan"


def test_reconcile_giveup_scans(db, root):
    """对账变更 >500：放弃增量、索引保留原状、本次整轮直扫且仍出结果。"""
    for i in range(600):
        (root / f"gen{i:03d}.txt").write_text("alpha_marker = 1\n", encoding="utf-8")
    row = _folder(db, root)
    first = ff.search_files(db, row, "alpha_marker")   # 首建（605 个可索引文件 < 2000）
    assert first["ok"] is True and first["mode"] == "index"
    for i in range(501):
        (root / f"gen{i:03d}.txt").write_text("beta_marker = 2\n", encoding="utf-8")
    again = ff.search_files(db, row, "beta_marker")
    assert again["ok"] is True and again["mode"] == "scan" and again["total"] > 0
    assert any(m["rel_path"] == "gen000.txt" for m in again["matches"])


def test_purge_and_gc(db, root):
    """purge_folder 清该 folder 全部块；gc_orphans 清 folder 无主块并返回删除数。"""
    row = _folder(db, root)
    ff.search_files(db, row, "x = 1")   # 建索引
    mine = select(FolderFileChunk).where(FolderFileChunk.folder_id == row.id)
    assert db.scalars(mine).all()
    ff.purge_folder(db, row.id)
    assert db.scalars(mine).all() == []
    db.add(FolderFileChunk(folder_id=987654, rel_path="orphan.txt", mtime=0.0, size=0,
                           line_start=1, line_end=1, content="orphan"))
    db.commit()
    purged = ff.gc_orphans(make_session_factory(db.get_bind()))
    assert purged == 1
    assert db.scalars(select(FolderFileChunk)
                      .where(FolderFileChunk.folder_id == 987654)).all() == []
