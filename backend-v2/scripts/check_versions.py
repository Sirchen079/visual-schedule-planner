"""版本一致性校验与统一写入。

单一事实源是仓库根 VERSION；下列声明必须与它一致：
  backend-v2/pyproject.toml                [project].version
  backend-v2/src/zhishi/__init__.py        __version__（/health 与实际运行版本）
  electron-v2/package.json                 version（安装包与自动更新版本）
  electron-v2/package-lock.json            version 与 packages[""].version
  backend-v2/docs/contracts/openapi.json   info.version（契约快照，由 export_contracts.py 生成）
  README.md                                Windows x64 · <版本> · MIT 开源
  backend-v2/README.md                     当前版本
  electron-v2/README.md                    当前版本

测试与打包验证脚本不在此列：它们直接读 VERSION 或 zhishi.__version__，不重复字面量。

用法：
  python scripts/check_versions.py                校验；不一致 exit 1
  python scripts/check_versions.py --set 2.25.0   统一写入；随后重跑 export_contracts.py
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
_VERSION_GROUP = r"(\d+\.\d+\.\d+)"

# (标签, 相对路径, 取值方式, 就地重写正则, 替换模板, 是否生成物)
# 生成物不就地改写：内容只能由 export_contracts.py 重新生成。
SPECS: tuple[tuple, ...] = (
    ("VERSION", "VERSION", ("text",), r"^\S*", "{v}", False),
    ("backend-v2/pyproject.toml", "backend-v2/pyproject.toml",
     ("toml", "project", "version"), r'^version = "[^"]+"', 'version = "{v}"', False),
    ("backend-v2/src/zhishi/__init__.py", "backend-v2/src/zhishi/__init__.py",
     ("regex", rf'^__version__ = "{_VERSION_GROUP}"'), r'^__version__ = "[^"]+"',
     '__version__ = "{v}"', False),
    ("electron-v2/package.json", "electron-v2/package.json",
     ("json", "version"), r'^  "version": "[^"]+",', '  "version": "{v}",', False),
    ("electron-v2/package-lock.json", "electron-v2/package-lock.json",
     ("json", "version"), r'^  "version": "[^"]+",', '  "version": "{v}",', False),
    ('electron-v2/package-lock.json packages[""]', "electron-v2/package-lock.json",
     ("json", "packages", "", "version"), r'^      "version": "[^"]+",',
     '      "version": "{v}",', False),
    ("backend-v2/docs/contracts/openapi.json", "backend-v2/docs/contracts/openapi.json",
     ("json", "info", "version"), "", "", True),
    ("README.md", "README.md",
     ("regex", rf"^\*\*Windows x64 · {_VERSION_GROUP} · MIT 开源\*\*$"),
     r"^\*\*Windows x64 · \d+\.\d+\.\d+ · MIT 开源\*\*",
     "**Windows x64 · {v} · MIT 开源**", False),
    ("backend-v2/README.md", "backend-v2/README.md",
     ("regex", rf"^当前版本 {_VERSION_GROUP}。"), r"^当前版本 \d+\.\d+\.\d+。",
     "当前版本 {v}。", False),
    ("electron-v2/README.md", "electron-v2/README.md",
     ("regex", rf"^当前版本 {_VERSION_GROUP}。"), r"^当前版本 \d+\.\d+\.\d+。",
     "当前版本 {v}。", False),
)


@dataclass(frozen=True)
class Report:
    target: str
    rows: tuple[tuple[str, str | None], ...]

    @property
    def ok(self) -> bool:
        return not self.mismatches()

    def mismatches(self) -> list[tuple[str, str | None]]:
        return [(label, value) for label, value in self.rows if value != self.target]

    def render(self) -> str:
        lines = [f"[versions] VERSION = {self.target}"]
        for label, value in self.rows:
            shown = value if value is not None else "读取失败"
            lines.append(f"  {'OK  ' if value == self.target else '差异'} {label} = {shown}")
        return "\n".join(lines)


def _dig(data, keys):
    for key in keys:
        data = data[key]
    return data


def _value(path: Path, getter: tuple) -> str:
    kind, *rest = getter
    if kind == "text":
        return path.read_text(encoding="utf-8").strip()
    if kind == "toml":
        with path.open("rb") as stream:
            return str(_dig(tomllib.load(stream), rest))
    if kind == "json":
        return str(_dig(json.loads(path.read_text(encoding="utf-8")), rest))
    if kind == "regex":
        match = re.search(rest[0], path.read_text(encoding="utf-8"), re.M)
        if match is None:
            raise ValueError(f"未匹配 {rest[0]}")
        return match.group(1)
    raise ValueError(f"未知取值方式：{kind}")


def check(root: Path = REPO_ROOT) -> Report:
    """逐项读取声明值；文件缺失或格式不符记为「读取失败」并参与判定。"""
    target = (root / "VERSION").read_text(encoding="utf-8").strip()
    rows: list[tuple[str, str | None]] = []
    for label, relative, getter, *_ in SPECS:
        try:
            rows.append((label, _value(root / relative, getter)))
        except (OSError, ValueError, KeyError, TypeError):
            rows.append((label, None))
    return Report(target, tuple(rows))


def apply(root: Path, version: str) -> list[str]:
    """把 version 写入各声明文件，返回跳过的生成物标签。

    以 newline="" 读写：不翻译换行符，避免 Windows 上把 LF 文件改成 CRLF。
    """
    skipped: list[str] = []
    for label, relative, _getter, pattern, template, generated in SPECS:
        if generated or not pattern:
            skipped.append(label)
            continue
        path = root / relative
        with open(path, encoding="utf-8", newline="") as stream:
            text = stream.read()
        updated, count = re.subn(pattern, template.format(v=version), text,
                                 count=1, flags=re.M)
        if count != 1:
            raise SystemExit(f"[versions] 未能在 {relative} 定位版本号（模式 {pattern}），请手动检查")
        with open(path, "w", encoding="utf-8", newline="") as stream:
            stream.write(updated)
    return skipped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验/统一各版本声明（单一事实源：根 VERSION）")
    parser.add_argument("--set", dest="new_version", metavar="X.Y.Z",
                        help="把新版本号写入各声明文件（契约快照需另跑 export_contracts.py）")
    args = parser.parse_args(argv)

    try:
        report = check()
    except OSError as exc:
        print(f"[versions] 无法读取 {REPO_ROOT / 'VERSION'}：{exc}", file=sys.stderr)
        return 1

    if args.new_version is not None:
        if not SEMVER.match(args.new_version):
            print(f"[versions] 版本号须为 X.Y.Z：{args.new_version}", file=sys.stderr)
            return 2
        skipped = apply(REPO_ROOT, args.new_version)
        report = check()
        print(f"[versions] 已写入 {args.new_version}；"
              f"共校验 {len(report.rows)} 处声明")
        if report.mismatches():
            print("[versions] 待更新（生成物，需重新生成）：" + "、".join(skipped))
            print("[versions] 运行 python scripts/export_contracts.py 后重跑本脚本确认")
            return 0
        return 0

    print(report.render())
    if report.ok:
        print(f"[versions] 通过：{len(report.rows)} 处声明与 VERSION 一致")
        return 0
    detail = "、".join(f"{label}（{value if value is not None else '读取失败'}）"
                       for label, value in report.mismatches())
    print(f"[versions] 不一致：{detail}", file=sys.stderr)
    print(f"[versions] 统一版本号：python scripts/check_versions.py --set {report.target}",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
