"""运行：python scripts/export_contracts.py —— 生成契约物料：
docs/contracts/events.schema.json（权威 JSON Schema）
docs/contracts/events.d.ts（前端 TypeScript 类型，原生生成器，零外部依赖）
docs/contracts/openapi.json（REST 契约快照，需应用可导入）
"""
import json
from pathlib import Path

from zhishi.agent.events import schema_union

CONTRACTS = Path("docs/contracts")

# ---- TypeScript 原生生成 ----

_TS_PRIMITIVES = {int: "number", float: "number", str: "string", bool: "boolean"}


def _ts_type(annotation) -> str:
    import types as _types
    import typing
    if annotation in _TS_PRIMITIVES:
        return _TS_PRIMITIVES[annotation]
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin is typing.Literal:
        return " | ".join(json.dumps(v) for v in args)
    if origin in (list,):
        return f"Array<{_ts_type(args[0])}>"
    if origin is dict:
        return "Record<string, unknown>"
    if origin is _types.UnionType or origin is typing.Union:
        parts = [_ts_type(a) for a in args if a is not type(None)]
        tail = " | null" if type(None) in args else ""
        return " | ".join(parts) + tail
    return "unknown"


def _ts_doc(comment: str) -> list[str]:
    lines = []
    wrapped = comment if comment else ""
    if wrapped:
        lines.append("  /** " + wrapped.replace("\n", " ") + " */")
    return lines


def export_typescript() -> Path:
    from zhishi.agent.events import ALL_EVENTS
    blocks = [
        "/* eslint-disable */",
        "/** 知时 SSE 事件契约 v1 —— 由 scripts/export_contracts.py 自动生成，勿手改。",
        " * 权威定义：src/zhishi/agent/events.py；每帧格式：event: <type>\\ndata: <json>\\n\\n",
        " * 判别联合按 type 字段收窄。 */",
        "",
    ]
    names = []
    for m in ALL_EVENTS:
        names.append(m.__name__)
        blocks.append(f"export interface {m.__name__} {{")
        doc = (m.__doc__ or "").strip()
        if doc:
            blocks.append(f"  /** {doc.splitlines()[0]} */")
        for key, field in m.model_fields.items():
            # type/v 在线上帧中恒存在（Pydantic 默认值序列化时总是输出），TS 侧必须必填
            optional = not field.is_required() and key not in ("type", "v")
            t = _ts_type(field.annotation)
            line = f"  {key}{'?' if optional else ''}: {t};"
            desc = field.description
            if desc:
                blocks.append(f"  /** {desc} */")
            blocks.append(line)
        blocks.append("}")
        blocks.append("")
    blocks.append("export type SSEEvent =\n  | " + "\n  | ".join(names) + ";")
    blocks.append("")
    out = CONTRACTS / "events.d.ts"
    out.write_text("\n".join(blocks), encoding="utf-8")
    return out


def _strip_leaked_sse_media_type(spec: dict) -> None:
    """FastAPI 会把 route.response_class 的媒体类型泄漏进 route.responses 声明的
    错误响应（resume 400 实为 JSON body，SSE 只属于 200 流）。
    非流式状态码的 content 若同时出现 application/json 与 text/event-stream，删后者。"""
    for path_item in spec.get("paths", {}).values():
        for method in ("get", "post", "put", "patch", "delete"):
            op = path_item.get(method)
            if not isinstance(op, dict):
                continue
            for status, resp in op.get("responses", {}).items():
                if status in ("200", "201", "202", "default"):
                    continue
                content = resp.get("content") or {}
                if "application/json" in content:
                    content.pop("text/event-stream", None)


def export_openapi() -> Path | None:
    try:
        import tempfile
        from zhishi.server.app import create_app
        import json as _json
        with tempfile.TemporaryDirectory() as td:
            app = create_app(data_dir=Path(td))
            spec = app.openapi()
            _strip_leaked_sse_media_type(spec)
            out = CONTRACTS / "openapi.json"
            out.write_text(_json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
            return out
    except Exception as exc:  # noqa: BLE001
        print(f"WARN: OpenAPI 快照失败: {exc}")
        return None


def main() -> None:
    CONTRACTS.mkdir(parents=True, exist_ok=True)
    schema_path = CONTRACTS / "events.schema.json"
    schema_path.write_text(json.dumps(schema_union(), ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(f"written: {schema_path}")
    print(f"written: {export_typescript()}")
    api = export_openapi()
    if api:
        print(f"written: {api}")


if __name__ == "__main__":
    from typing import Literal  # noqa: F401 确保 Literal 可被 _ts_type 引用
    main()
