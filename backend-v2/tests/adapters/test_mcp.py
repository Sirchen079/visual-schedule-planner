"""MCP 适配、权限检查与管理路由测试。
stdio 用例启动测试子进程；其他用例使用进程内服务器。"""
import json
import os
import sys

import pytest

CHILD_SCRIPT = '''\
import asyncio
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

server = MCPServer(name="stdio-tools")

def add(a: int, b: int) -> int:
    """加法"""
    return a + b

def del_file(path: str) -> str:
    """删除文件"""
    return f"deleted {path}"

server.add_tool(add, name="add", description="加法",
                annotations=ToolAnnotations(read_only_hint=True))
server.add_tool(del_file, name="del_file", description="删除文件")

async def main():
    await server.run_stdio_async()

asyncio.run(main())
'''


def _make_server():
    """in-process MCP 服务器（SDK v2 MCPServer；与 prod 同走 MCPToolset 代码路径）。"""
    from mcp.server.mcpserver import MCPServer
    from mcp.types import ToolAnnotations
    server = MCPServer(name="tools")

    def add(a: int, b: int) -> int:
        """加法"""
        return a + b

    def del_file(path: str) -> str:
        """删除文件"""
        return f"deleted {path}"

    server.add_tool(add, name="add", description="加法",
                    annotations=ToolAnnotations(read_only_hint=True))
    server.add_tool(del_file, name="del_file", description="删除文件")
    return server


def _server_row(db, **kw):
    from zhishi.domain.models import MCPServer
    params = dict(transport="http", url="http://localhost:9/mcp", enabled=True)
    params.update(kw)
    row = MCPServer(name=params.pop("name", "srv"), **params)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture()
def stdio_row(db, tmp_path):
    script = tmp_path / "mcp_stdio_child.py"
    script.write_text(CHILD_SCRIPT, encoding="utf-8")
    return _server_row(db, name="stdio", transport="stdio", command=sys.executable,
                       args_json=json.dumps([str(script)]), timeout_sec=30)


def _count_connections(monkeypatch, server=None):
    """给 mcp_client.build_client 套连接计数（每次真实构造 client 记一次）。
    server 给定时同时注入 in-process 服务器（路由级测试用）；
    否则转发原 build_client（stdio 真子进程路径）。"""
    from zhishi.adapters import mcp_client
    orig = mcp_client.build_client
    calls = {"n": 0}

    def _spy(row):
        calls["n"] += 1
        return (server, {}) if server is not None else orig(row)

    monkeypatch.setattr(mcp_client, "build_client", _spy)
    return calls


# ---- 适配器：真实 stdio 子进程 ----

async def test_list_tools_stdio(db, stdio_row):
    from zhishi.adapters import mcp_client
    tools = await mcp_client.list_tools(stdio_row)
    by_name = {t["name"]: t for t in tools}
    assert {"add", "del_file"} <= set(by_name)
    assert "a" in by_name["add"]["input_schema"]["properties"]
    assert by_name["add"]["read_only"] is True
    assert by_name["del_file"]["read_only"] is False


async def test_call_tool_stdio(db, stdio_row):
    from zhishi.adapters import mcp_client
    out = await mcp_client.call_tool(stdio_row, "add", {"a": 2, "b": 3})
    assert "5" in out


async def test_error_sanitized_and_capped(db, tmp_path):
    """错误文本不得包含 env/headers 值，且截断至 300 字符。"""
    from zhishi.adapters import mcp_client
    row = _server_row(db, name="bad", transport="stdio", command=sys.executable,
                      args_json=json.dumps(["-c", "import sys; sys.exit(1)"]),
                      env_json=json.dumps({"MY_TOKEN": "supersecret99"}))
    with pytest.raises(mcp_client.MCPClientError) as ei:
        await mcp_client.list_tools(row)
    msg = str(ei.value)
    assert "supersecret99" not in msg
    assert len(msg) <= 300


async def test_call_tool_result_capped(db, stdio_row):
    from zhishi.adapters import mcp_client
    out = await mcp_client.call_tool(stdio_row, "add", {"a": 2, "b": 3})
    assert len(out) <= 4000


# ---- runtime 注入与权限门（in-process 服务器） ----

def _patch_server(monkeypatch, server):
    from zhishi.adapters import mcp_client
    monkeypatch.setattr(mcp_client, "build_client", lambda row: (server, {}))


async def test_runtime_injects_namespaced_mcp_tools(db, monkeypatch):
    server = _make_server()
    row = _server_row(db, auto_approve_readonly=True)
    _patch_server(monkeypatch, server)
    from pydantic_ai.models.function import FunctionModel
    from zhishi.agent.runtime import AgentRuntime

    seen = {}

    async def stream(messages, info):
        seen["names"] = [t.name for t in info.function_tools]
        yield "好的"

    rt = AgentRuntime(model=FunctionModel(stream_function=stream), db=db)
    events = [e async for e in rt.run_stream(user_text="有什么工具")]
    assert f"mcp__{row.id}__add" in seen["names"]
    assert f"mcp__{row.id}__del_file" in seen["names"]


async def test_mcp_disabled_server_not_injected(db, monkeypatch):
    server = _make_server()
    row = _server_row(db, enabled=False)
    _patch_server(monkeypatch, server)
    from pydantic_ai.models.function import FunctionModel
    from zhishi.agent.runtime import AgentRuntime

    seen = {}

    async def stream(messages, info):
        seen["names"] = [t.name for t in info.function_tools]
        yield "好的"

    rt = AgentRuntime(model=FunctionModel(stream_function=stream), db=db)
    _ = [e async for e in rt.run_stream(user_text="有什么工具")]
    assert not any(n.startswith("mcp__") for n in seen["names"])
    _ = row


async def test_mcp_readonly_direct_when_auto_approve(db, monkeypatch):
    server = _make_server()
    row = _server_row(db, auto_approve_readonly=True)
    _patch_server(monkeypatch, server)
    from pydantic_ai.models.function import DeltaToolCall, FunctionModel
    from zhishi.agent.runtime import AgentRuntime

    step = {"n": 0}

    async def stream(messages, info):
        step["n"] += 1
        if step["n"] == 1:
            yield {0: DeltaToolCall(name=f"mcp__{row.id}__add",
                                    json_args=json.dumps({"a": 1, "b": 2}),
                                    tool_call_id="t1")}
        else:
            yield "算完了"

    rt = AgentRuntime(model=FunctionModel(stream_function=stream), db=db)
    events = [e async for e in rt.run_stream(user_text="算加法")]
    results = [e for e in events if e["type"] == "tool_call_result"]
    assert results and "3" in results[0]["result_preview"]
    assert not any(e["type"] == "tool_approval_requested" for e in events)


async def test_mcp_non_readonly_requires_approval(db, monkeypatch):
    server = _make_server()
    row = _server_row(db, auto_approve_readonly=True)
    _patch_server(monkeypatch, server)
    from pydantic_ai.models.function import DeltaToolCall, FunctionModel
    from zhishi.agent.runtime import AgentRuntime

    async def stream(messages, info):
        yield {0: DeltaToolCall(name=f"mcp__{row.id}__del_file",
                                json_args=json.dumps({"path": "a.txt"}),
                                tool_call_id="t2")}

    rt = AgentRuntime(model=FunctionModel(stream_function=stream), db=db)
    events = [e async for e in rt.run_stream(user_text="删文件")]
    approvals = [e for e in events if e["type"] == "tool_approval_requested"]
    assert approvals and approvals[0]["tool"] == f"mcp__{row.id}__del_file"
    done = next(e for e in events if e["type"] == "run_completed")
    assert done["done_reason"] == "awaiting_approval"


async def test_mcp_readonly_confirms_without_auto_approve(db, monkeypatch):
    server = _make_server()
    row = _server_row(db, auto_approve_readonly=False)
    _patch_server(monkeypatch, server)
    from pydantic_ai.models.function import DeltaToolCall, FunctionModel
    from zhishi.agent.runtime import AgentRuntime

    async def stream(messages, info):
        yield {0: DeltaToolCall(name=f"mcp__{row.id}__add",
                                json_args=json.dumps({"a": 1, "b": 2}),
                                tool_call_id="t3")}

    rt = AgentRuntime(model=FunctionModel(stream_function=stream), db=db)
    events = [e async for e in rt.run_stream(user_text="算加法")]
    assert any(e["type"] == "tool_approval_requested" for e in events)


async def test_mcp_grant_skips_approval_end_to_end(db, monkeypatch):
    """MCP 工具接入 grants——预置「始终允许」（命名空间全名 + 空模式）
    后真流直连执行，不再落审批卡片（auto_approve_readonly=False 照样生效）。"""
    from zhishi.domain.models import AIToolGrant
    server = _make_server()
    row = _server_row(db, auto_approve_readonly=False)
    db.add(AIToolGrant(tool_name=f"mcp__{row.id}__add", arg_pattern="")); db.commit()
    _patch_server(monkeypatch, server)
    from pydantic_ai.models.function import DeltaToolCall, FunctionModel
    from zhishi.agent.runtime import AgentRuntime

    async def stream(messages, info):
        yield {0: DeltaToolCall(name=f"mcp__{row.id}__add",
                                json_args=json.dumps({"a": 1, "b": 2}),
                                tool_call_id="t4")}

    rt = AgentRuntime(model=FunctionModel(stream_function=stream), db=db)
    events = [e async for e in rt.run_stream(user_text="算加法")]
    results = [e for e in events if e["type"] == "tool_call_result"]
    assert results and "3" in results[0]["result_preview"]
    assert not any(e["type"] == "tool_approval_requested" for e in events)


# ---- 管理路由 ----

def test_mcp_server_crud_and_test_endpoint(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from zhishi.domain.models import MCPServer
    from zhishi.server.app import create_app

    with TestClient(create_app(data_dir=tmp_path)) as c:
        r = c.post("/ai/mcp/servers", json={
            "name": "srv", "transport": "http", "url": "http://localhost:9999/mcp",
            "auto_approve_readonly": True})
        assert r.status_code == 201
        sid = r.json()["id"]

        r = c.get("/ai/mcp/servers")
        assert any(x["id"] == sid and x["last_status"] == "untested" for x in r.json())

        r = c.put(f"/ai/mcp/servers/{sid}", json={"timeout_sec": 45})
        assert r.json()["timeout_sec"] == 45

        r = c.post(f"/ai/mcp/servers/{sid}/enable", json={"enabled": False})
        assert r.json()["ok"] is True
        with c.app.state.session_factory() as db:
            assert db.get(MCPServer, sid).enabled is False
        c.post(f"/ai/mcp/servers/{sid}/enable", json={"enabled": True})

        # test 端点：注入 in-process 服务器 → 连接 + list_tools 回写 last_status
        _patch_server(monkeypatch, _make_server())
        r = c.post(f"/ai/mcp/servers/{sid}/test")
        assert r.status_code == 200 and r.json()["ok"] is True
        assert r.json()["tool_count"] == 2
        with c.app.state.session_factory() as db:
            assert db.get(MCPServer, sid).last_status == "ok"

        r = c.get(f"/ai/mcp/servers/{sid}/tools")
        assert r.status_code == 200
        assert {t["name"] for t in r.json()} == {"add", "del_file"}

        r = c.delete(f"/ai/mcp/servers/{sid}")
        assert r.status_code == 204
        assert c.get("/ai/mcp/servers").json() == []


def test_mcp_test_endpoint_failure_writes_last_error(tmp_path):
    from fastapi.testclient import TestClient
    from zhishi.domain.models import MCPServer
    from zhishi.server.app import create_app

    with TestClient(create_app(data_dir=tmp_path)) as c:
        r = c.post("/ai/mcp/servers", json={
            "name": "bad", "transport": "stdio", "command": sys.executable,
            "args_json": json.dumps(["-c", "import sys; sys.exit(1)"]),
            "env_json": json.dumps({"MY_TOKEN": "supersecret99"}), "trusted": True})
        sid = r.json()["id"]
        r = c.post(f"/ai/mcp/servers/{sid}/test")
        assert r.status_code == 200 and r.json()["ok"] is False
        err = r.json()["error"]
        assert "supersecret99" not in err and len(err) <= 300
        with c.app.state.session_factory() as db:
            row = db.get(MCPServer, sid)
            assert row.last_status == "error" and "supersecret99" not in (row.last_error or "")


# ---- stdio 显式信任（无认证本地服务下防止任意进程拉起） ----

def test_untrusted_stdio_test_endpoint_rejected(tmp_path, monkeypatch):
    """untrusted stdio：/test 与 /tools 拒绝且不拉起子进程；显式信任后放行。"""
    from fastapi.testclient import TestClient
    from zhishi.domain.models import MCPServer
    from zhishi.server.app import create_app

    with TestClient(create_app(data_dir=tmp_path)) as c:
        r = c.post("/ai/mcp/servers", json={
            "name": "stdio-untrusted", "transport": "stdio", "command": sys.executable,
            "args_json": json.dumps(["-c", "import sys; sys.exit(1)"])})
        assert r.status_code == 201
        sid = r.json()["id"]

        # 默认 untrusted：/test 403（明确提示需在配置中确认），不尝试连接
        r = c.post(f"/ai/mcp/servers/{sid}/test")
        assert r.status_code == 403
        assert "信任" in r.json()["detail"]
        # /tools 同样拒绝（也会拉起子进程）
        assert c.get(f"/ai/mcp/servers/{sid}/tools").status_code == 403
        # 列表回显 trusted 标记（默认 False）
        rows = c.get("/ai/mcp/servers").json()
        assert any(x["id"] == sid and x["trusted"] is False for x in rows)
        with c.app.state.session_factory() as db:
            assert db.get(MCPServer, sid).last_status == "untested"  # 未真正连接

        # 用户在配置中显式信任 → /test 正常连接（注入 in-process 服务器验证）
        _patch_server(monkeypatch, _make_server())
        r = c.put(f"/ai/mcp/servers/{sid}", json={"trusted": True})
        assert r.status_code == 200 and r.json()["trusted"] is True
        r = c.post(f"/ai/mcp/servers/{sid}/test")
        assert r.status_code == 200 and r.json()["ok"] is True


async def test_runtime_skips_untrusted_stdio_assembly(db, monkeypatch):
    """untrusted stdio 服务器不进工具装配（连 client 都不构造 → 不可能拉起进程）；
    trusted=True 后恢复装配。http 传输不受限。"""
    from pydantic_ai.models.function import FunctionModel
    from zhishi.adapters import mcp_client
    from zhishi.agent.runtime import AgentRuntime

    server = _make_server()
    built: list[int] = []

    def _spy(row):
        built.append(row.id)
        return (server, {})

    monkeypatch.setattr(mcp_client, "build_client", _spy)
    row = _server_row(db, name="stdio", transport="stdio",
                      command="no-such-binary", enabled=True, trusted=False)
    http_row = _server_row(db, name="http", transport="http",
                           url="http://localhost:9/mcp", enabled=True)

    seen: dict = {}

    async def stream(messages, info):
        seen["names"] = [t.name for t in info.function_tools]
        yield "好的"

    rt = AgentRuntime(model=FunctionModel(stream_function=stream), db=db)
    _ = [e async for e in rt.run_stream(user_text="有什么工具")]
    assert built == [http_row.id]                       # untrusted stdio 未构造 client
    assert not any(n.startswith(f"mcp__{row.id}__") for n in seen["names"])
    assert f"mcp__{http_row.id}__add" in seen["names"]  # http 不受限

    row.trusted = True
    db.commit()
    built.clear()
    rt2 = AgentRuntime(model=FunctionModel(stream_function=stream), db=db)
    _ = [e async for e in rt2.run_stream(user_text="有什么工具")]
    assert set(built) == {http_row.id, row.id}          # trusted 后恢复装配（顺序不限）
    assert f"mcp__{row.id}__add" in seen["names"]


# ---- 工具清单 60s TTL 缓存（/tools 与 runtime 装配不再每次真连） ----

async def test_list_tools_cache_hits_within_ttl(db, stdio_row, monkeypatch):
    """TTL 内两次 list_tools 只真实连接一次（stdiio 真子进程路径）。"""
    from zhishi.adapters import mcp_client
    calls = _count_connections(monkeypatch)
    t1 = await mcp_client.list_tools(stdio_row)
    t2 = await mcp_client.list_tools(stdio_row)
    assert calls["n"] == 1
    assert t1 == t2
    assert {t["name"] for t in t2} >= {"add", "del_file"}


async def test_list_tools_cache_expires_after_ttl(db, stdio_row, monkeypatch):
    """TTL 过期重连：59s 时仍命中，跨过 60s 后重连。"""
    from zhishi.adapters import mcp_client
    now = {"t": 1000.0}
    monkeypatch.setattr(mcp_client, "monotonic", lambda: now["t"])
    calls = _count_connections(monkeypatch)
    await mcp_client.list_tools(stdio_row)
    now["t"] += 59
    await mcp_client.list_tools(stdio_row)
    assert calls["n"] == 1                              # TTL 内命中
    now["t"] += 2                                       # 累计 61s > 60s TTL
    await mcp_client.list_tools(stdio_row)
    assert calls["n"] == 2                              # 过期重连


def test_mcp_route_cache_invalidation_on_update_enable_delete(tmp_path, monkeypatch):
    """路由层失效钩子：PUT 行更新 / enable 切换 / DELETE 都清该 server 缓存。
    DELETE 后新建 server 复用同一 id（sqlite rowid 复用），不得命中旧缓存。"""
    from fastapi.testclient import TestClient
    from zhishi.adapters import mcp_client
    from zhishi.server.app import create_app

    server = _make_server()
    calls = _count_connections(monkeypatch, server=server)

    with TestClient(create_app(data_dir=tmp_path)) as c:
        r = c.post("/ai/mcp/servers", json={
            "name": "srv", "transport": "http", "url": "http://localhost:9/mcp"})
        sid = r.json()["id"]

        assert c.get(f"/ai/mcp/servers/{sid}/tools").status_code == 200
        assert c.get(f"/ai/mcp/servers/{sid}/tools").status_code == 200
        assert calls["n"] == 1                          # GET /tools 走缓存

        c.put(f"/ai/mcp/servers/{sid}", json={"timeout_sec": 45})
        assert c.get(f"/ai/mcp/servers/{sid}/tools").status_code == 200
        assert calls["n"] == 2                          # PUT 失效 → 重连

        c.post(f"/ai/mcp/servers/{sid}/enable", json={"enabled": False})
        assert c.get(f"/ai/mcp/servers/{sid}/tools").status_code == 200
        assert calls["n"] == 3                          # enable 切换失效 → 重连

        r = c.delete(f"/ai/mcp/servers/{sid}")
        assert r.status_code == 204
        r = c.post("/ai/mcp/servers", json={
            "name": "srv2", "transport": "http", "url": "http://localhost:9/mcp"})
        sid2 = r.json()["id"]
        assert sid2 == sid                              # sqlite rowid 复用，缓存键相同
        assert c.get(f"/ai/mcp/servers/{sid2}/tools").status_code == 200
        assert calls["n"] == 4                          # DELETE 失效 → 新行也重连


def test_mcp_test_endpoint_bypasses_cache(tmp_path, monkeypatch):
    """/test 连通性测试不走缓存：意义就是真连，两次调用连接两次（不读也不写）。"""
    from fastapi.testclient import TestClient
    from zhishi.adapters import mcp_client
    from zhishi.server.app import create_app

    server = _make_server()
    calls = _count_connections(monkeypatch, server=server)

    with TestClient(create_app(data_dir=tmp_path)) as c:
        r = c.post("/ai/mcp/servers", json={
            "name": "srv", "transport": "http", "url": "http://localhost:9/mcp"})
        sid = r.json()["id"]

        r = c.post(f"/ai/mcp/servers/{sid}/test")
        assert r.status_code == 200 and r.json()["ok"] is True
        r = c.post(f"/ai/mcp/servers/{sid}/test")
        assert r.status_code == 200 and r.json()["ok"] is True
        assert calls["n"] == 2                          # /test 每次真连

        assert c.get(f"/ai/mcp/servers/{sid}/tools").status_code == 200
        assert calls["n"] == 3                          # /test 未写缓存，/tools 需自连


# ---- GatedToolset（run 装配路径）复用同一模块级 TTL 缓存 ----

def _count_client_connects(monkeypatch):
    """给 fastmcp.Client.__aenter__ 套计数（每次真实建立会话记一次；
    框架嵌套进入同一已连 client 时不会重复触发 __aenter__ 的连接）。"""
    import fastmcp
    orig = fastmcp.Client.__aenter__
    connects = {"n": 0}

    async def counting_enter(self):
        connects["n"] += 1
        return await orig(self)

    monkeypatch.setattr(fastmcp.Client, "__aenter__", counting_enter)
    return connects


async def test_gated_toolset_two_runs_connect_once(db, monkeypatch):
    """run 装配每次新建 toolset 实例（框架实例级 cache_tools 随 __aexit__ 失效）：
    两次 run 触发列工具只真连一次；invalidate（PUT/enable/DELETE 失效钩子同款）
    后重新真连。缓存命中路径还原的命名空间工具清单仍完整可用。"""
    from pydantic_ai.models.function import FunctionModel
    from zhishi.adapters import mcp_client
    from zhishi.agent.runtime import AgentRuntime

    server = _make_server()
    row = _server_row(db)
    _patch_server(monkeypatch, server)
    connects = _count_client_connects(monkeypatch)

    seen: dict = {}

    async def stream(messages, info):
        seen["names"] = [t.name for t in info.function_tools]
        yield "好的"

    for _ in range(2):   # 两次独立装配 = 两个 GatedToolset 实例（模拟两次 run）
        rt = AgentRuntime(model=FunctionModel(stream_function=stream), db=db)
        _ = [e async for e in rt.run_stream(user_text="有什么工具")]
        assert f"mcp__{row.id}__add" in seen["names"]
    assert connects["n"] == 1                       # 第二次 run 命中模块级缓存，不再真连

    mcp_client.invalidate(row.id)                   # 路由 PUT/enable/DELETE 钩子同款
    rt = AgentRuntime(model=FunctionModel(stream_function=stream), db=db)
    _ = [e async for e in rt.run_stream(user_text="有什么工具")]
    assert connects["n"] == 2                       # 失效后重新真连


async def test_gated_toolset_call_tool_still_connects(db, monkeypatch):
    """工具调用不缓存（必要行为）：清单命中缓存（列取零连接）后，
    真实工具调用仍按需连接执行。"""
    from pydantic_ai.models.function import DeltaToolCall, FunctionModel
    from zhishi.adapters import mcp_client
    from zhishi.agent.runtime import AgentRuntime

    server = _make_server()
    row = _server_row(db, auto_approve_readonly=True)
    _patch_server(monkeypatch, server)
    connects = _count_client_connects(monkeypatch)

    warm = await mcp_client.list_tools(row)          # 预热模块级缓存（真连一次）
    assert {t["name"] for t in warm} == {"add", "del_file"}
    assert connects["n"] == 1

    async def stream(messages, info):
        yield {0: DeltaToolCall(name=f"mcp__{row.id}__add",
                                json_args=json.dumps({"a": 2, "b": 3}),
                                tool_call_id="t9")}

    rt = AgentRuntime(model=FunctionModel(stream_function=stream), db=db)
    events = [e async for e in rt.run_stream(user_text="算加法")]
    results = [e for e in events if e["type"] == "tool_call_result"]
    assert results and "5" in results[0]["result_preview"]   # 调用真实执行
    assert connects["n"] == 2                        # 仅工具调用按需连接（列取未连）


# ---- 缓存世代号——invalidate 后旧查询返回不得回填 ----
# list_tools miss 后 await 网络；若等待期间 PUT/DELETE 调了 invalidate，旧结果
# 无条件写回会污染缓存 60s（含 readOnlyHint，参与免审分类，是安全问题）。
# 修复：进入时捕获模块级世代号，网络返回后世代未变才写回，变了则丢弃。


def _fake_tool(name: str):
    import mcp.types as mcp_types
    return mcp_types.Tool(name=name, description="d",
                          input_schema={"type": "object", "properties": {}},
                          annotations=mcp_types.ToolAnnotations(read_only_hint=True))


async def test_list_tools_invalidate_during_query_discards_stale_result(db, monkeypatch):
    """受控 Event 暂停旧查询 → 期间 invalidate → 释放：旧结果正常返回但不得回填
    缓存；随后新查询真连（不命中旧结果）。"""
    import asyncio
    from zhishi.adapters import mcp_client

    server = _make_server()
    _patch_server(monkeypatch, server)               # 真连 = in-process 服务器
    row = _server_row(db)

    release = asyncio.Event()
    holder = {"tools": [_fake_tool("stale_tool")]}
    builds = {"n": 0}
    paused = {"on": True}

    class _PausedToolset:
        async def list_tools(self):
            await release.wait()                     # 模拟在途网络
            return holder["tools"]

    real_build = mcp_client.build_toolset

    def build(row_, timeout=None):
        builds["n"] += 1                              # 每次真连构造 client 记一次
        if paused["on"]:
            return _PausedToolset()
        return real_build(row_, timeout)

    monkeypatch.setattr(mcp_client, "build_toolset", build)

    task = asyncio.create_task(mcp_client.list_tools(row))
    for _ in range(5):
        await asyncio.sleep(0)                       # 让旧查询跑到网络等待点
    assert builds["n"] == 1

    mcp_client.invalidate(row.id)                    # 期间 PUT/DELETE 失效钩子
    release.set()
    stale = await task
    assert {t["name"] for t in stale} == {"stale_tool"}   # 旧查询自身正常返回
    assert row.id not in mcp_client._tools_cache          # 但世代已变：不得回填

    paused["on"] = False
    fresh = await mcp_client.list_tools(row)
    assert builds["n"] == 2                          # 缓存未被旧结果污染 → 真连
    assert {t["name"] for t in fresh} == {"add", "del_file"}


async def test_gated_toolset_invalidate_during_query_discards_stale_result(db, monkeypatch):
    """GatedToolset（run 装配路径）共用同一世代规则：覆写点先捕获后校验，
    invalidate 后旧查询不回填、新查询重新真连。"""
    import asyncio
    from zhishi.adapters import mcp_client
    from zhishi.agent.runtime import _MCPGatedToolset

    row = _server_row(db)
    release = asyncio.Event()
    holder = {"tools": [_fake_tool("stale_tool")]}
    connects = {"n": 0}

    async def paused_connected(self):
        connects["n"] += 1
        await release.wait()
        return holder["tools"]

    monkeypatch.setattr(_MCPGatedToolset, "_list_tools_connected", paused_connected)
    toolset = _MCPGatedToolset("http://localhost:9/mcp", server_id=row.id)

    task = asyncio.create_task(toolset.list_tools())
    for _ in range(5):
        await asyncio.sleep(0)
    assert connects["n"] == 1

    mcp_client.invalidate(row.id)
    release.set()
    stale = await task
    assert [t.name for t in stale] == ["stale_tool"]
    assert row.id not in mcp_client._tools_cache     # 世代已变：不得回填

    holder["tools"] = [_fake_tool("fresh_tool")]
    fresh = await toolset.list_tools()
    assert connects["n"] == 2                        # 未命中被污染缓存 → 重连
    assert [t.name for t in fresh] == ["fresh_tool"]
