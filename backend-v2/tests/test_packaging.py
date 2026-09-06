# tests/test_packaging.py
"""M5 回归：pydantic-ai-slim 必须带 mcp extra——runtime 顶层 import
pydantic_ai.mcp，干净环境缺 fastmcp 会在 MCP 代码路径直接崩溃。"""
import tomllib
from pathlib import Path


def test_pyproject_declares_mcp_extra():
    data = tomllib.loads(
        Path(__file__).resolve().parents[1].joinpath("pyproject.toml").read_text(encoding="utf-8"))
    deps = data["project"]["dependencies"]
    assert any("pydantic-ai-slim" in d and "mcp" in d for d in deps), \
        f"pydantic-ai-slim 缺 mcp extra：{[d for d in deps if 'pydantic-ai-slim' in d]}"
