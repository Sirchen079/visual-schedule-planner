"""folder_files 域层：忽略规则 walk、越权路径防护（../、绝对路径、symlink/junction 逃逸）、限界文本读取。"""
import sys
from pathlib import Path

import pytest

from zhishi.domain import folder_files as ff


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
