"""check_versions.py 的行为契约：能查出漂移、能统一写入、不误改其他内容。"""
import shutil
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import check_versions  # noqa: E402


@pytest.fixture
def repo(tmp_path):
    """以真实仓库为模板的临时副本：只拷贝被校验的文件，避免复制整个仓库。"""
    for _, relative, *_ in check_versions.SPECS:
        source = REPO_ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return tmp_path


def _write(root: Path, relative: str, text: str) -> None:
    (root / relative).write_text(text, encoding="utf-8", newline="")


def test_current_repository_is_consistent():
    report = check_versions.check()
    assert report.ok, report.render()
    assert report.target  # 版本号非空
    assert len(report.rows) == len(check_versions.SPECS)


@pytest.mark.parametrize("relative", [
    "backend-v2/src/zhishi/__init__.py",
    "electron-v2/package.json",
    "README.md",
])
def test_check_detects_drift(repo, relative):
    path = repo / relative
    current = check_versions.check(repo).target
    _write(repo, relative,
           path.read_text(encoding="utf-8").replace(current, "0.0.1"))
    report = check_versions.check(repo)
    assert not report.ok
    assert any(relative in label for label, _ in report.mismatches())


def test_check_reports_missing_file_as_failure(repo):
    (repo / "electron-v2/package.json").unlink()
    report = check_versions.check(repo)
    assert not report.ok
    assert ("electron-v2/package.json", None) in report.mismatches()


def test_apply_sets_every_declaration_and_keeps_other_text(repo):
    target = "9.9.9"
    _write(repo, "VERSION", target + "\n")
    skipped = check_versions.apply(repo, target)
    report = check_versions.check(repo)
    # 生成物（openapi.json）由 export_contracts.py 重生成，apply 只报告不就地改
    assert skipped == ["backend-v2/docs/contracts/openapi.json"]
    assert [label for label, _ in report.mismatches()] == skipped


def test_apply_does_not_translate_line_endings(repo):
    original = (repo / "README.md").read_bytes()
    check_versions.apply(repo, "9.9.9")
    updated = (repo / "README.md").read_bytes()
    assert updated.count(b"\r\n") == original.count(b"\r\n")
    assert updated.count(b"\n") == original.count(b"\n")


def test_apply_rejects_unlocatable_pattern(repo):
    _write(repo, "README.md", "# 没有版本标记的标题\n")
    with pytest.raises(SystemExit):
        check_versions.apply(repo, "9.9.9")


def test_version_format_validated():
    assert check_versions.SEMVER.match("2.24.0")
    for bad in ("2.24", "v2.24.0", "2.24.0-rc1", ""):
        assert check_versions.SEMVER.match(bad) is None
