# tests/server/test_mcp_grant_lifecycle.py
"""re #063 blocker：MCP grant 跨服务器继承。grants/pending 审批卡以 mcp__{sid}__{name}
为键，而 sid 是 sqlite rowid 可复用——删 A 建 B 得同 sid、或 PUT 把 A 的端点整个换成
B，旧「始终允许」与旧审批卡都不得为新服务器续命：
①删 A 重建 B 复用同 sid → 旧 grant 不生效（classify confirm）；
②PUT 改 url → 撤销（name/timeout 等非连接语义字段不撤销）；
③sid=1 撤销时 sid=10/11 保留（见 tests/agent/test_permissions.py 单元）；
④DELETE 后旧 pending action 变 expired 且 resume 不再回填它。"""
import json

from fastapi.testclient import TestClient
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from tests.server.test_ai_routes import parse_sse
from zhishi.server.app import create_app


def _in_process_server():
    """in-process MCP 服务器（与 tests/adapters/test_mcp.py 同款）。"""
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


def _patch_build_client(monkeypatch, server):
    from zhishi.adapters import mcp_client
    monkeypatch.setattr(mcp_client, "build_client", lambda row: (server, {}))


def _create_server(c, name: str) -> int:
    r = c.post("/ai/mcp/servers", json={
        "name": name, "transport": "http", "url": "http://localhost:9/mcp",
        "enabled": True})
    assert r.status_code == 201
    return r.json()["id"]


def _seed_grant(c, tool_name: str) -> None:
    """直接落一条「始终允许」（与 approve grant_always 同构：空模式=整工具）。"""
    from zhishi.domain.models import AIToolGrant
    with c.app.state.session_factory() as db:
        db.add(AIToolGrant(tool_name=tool_name, arg_pattern="")); db.commit()


def _mcp_grants(c, prefix: str) -> list:
    from sqlalchemy import select
    from zhishi.domain.models import AIToolGrant
    with c.app.state.session_factory() as db:
        rows = db.scalars(select(AIToolGrant)).all()
        return [r for r in rows if r.tool_name.startswith(prefix)]


def _classify_mcp(c, tool_name: str) -> str:
    from zhishi.agent.permissions import classify
    with c.app.state.session_factory() as db:
        return classify(db, tool_name, {"path": "a.txt"}, readonly_hint=False)


def test_delete_then_recreate_reusing_sid_does_not_inherit_grant(tmp_path):
    """①删 A 重建 B 复用同 sid → B 的同名工具不得沿用 A 的「始终允许」。"""
    with TestClient(create_app(data_dir=tmp_path)) as c:
        sid_a = _create_server(c, "srv-a")
        _seed_grant(c, f"mcp__{sid_a}__del_file")
        assert _classify_mcp(c, f"mcp__{sid_a}__del_file") == "allow"  # 前置：grant 生效

        assert c.delete(f"/ai/mcp/servers/{sid_a}").status_code == 204
        sid_b = _create_server(c, "srv-b")
        assert sid_b == sid_a, "前置失效：sqlite 未复用 rowid，本测试场景不成立"
        assert _classify_mcp(c, f"mcp__{sid_b}__del_file") == "confirm"


def test_put_transport_field_change_revokes_grants(tmp_path):
    """②PUT 改 url → 撤销该服务器全部 grants；name/timeout 等非连接语义字段变更
    不撤销；trusted 属连接语义（stdio 换可执行）同样撤销。"""
    with TestClient(create_app(data_dir=tmp_path)) as c:
        sid = _create_server(c, "srv")
        _seed_grant(c, f"mcp__{sid}__del_file")

        r = c.put(f"/ai/mcp/servers/{sid}", json={"url": "http://other-host:1234/mcp"})
        assert r.status_code == 200
        assert _mcp_grants(c, f"mcp__{sid}__") == []
        assert _classify_mcp(c, f"mcp__{sid}__del_file") == "confirm"

        _seed_grant(c, f"mcp__{sid}__del_file")
        r = c.put(f"/ai/mcp/servers/{sid}", json={"name": "srv-renamed", "timeout_sec": 99})
        assert r.status_code == 200
        assert len(_mcp_grants(c, f"mcp__{sid}__")) == 1, "非连接语义字段变更不得撤销"

        r = c.put(f"/ai/mcp/servers/{sid}", json={"trusted": True})
        assert r.status_code == 200
        assert _mcp_grants(c, f"mcp__{sid}__") == []


def test_delete_expires_pending_action_and_resume_refuses_backfill(tmp_path, monkeypatch):
    """④DELETE 后：该 sid 全部 pending 审批卡置 expired；旧卡不得再批准（404）、
    resume 不再回填它（400 typed consumed），堵死「旧卡批准 → resume 以
    tool_call_approved 绕权限门直执行新服务器同名工具」的继承链。"""
    server = _in_process_server()
    _patch_build_client(monkeypatch, server)

    with TestClient(create_app(data_dir=tmp_path)) as c:
        import zhishi.server.routes.ai as ai_route
        sid = _create_server(c, "srv")

        async def stream_del(messages, info):
            yield {0: DeltaToolCall(name=f"mcp__{sid}__del_file",
                                    json_args=json.dumps({"path": "a.txt"}),
                                    tool_call_id="tc1")}

        ai_route.build_model = lambda cfg, api_key=None: FunctionModel(
            stream_function=stream_del)
        from zhishi.domain.models import AIConfig
        with c.app.state.session_factory() as db:
            db.add(AIConfig(name="t", provider_kind="openai_compat", model="t",
                            base_url="http://x", enabled=True)); db.commit()

        events = parse_sse(c.post("/ai/chat/stream", json={"message": "删掉文件"}).text)
        approval = next(e for e in events if e["type"] == "tool_approval_requested")
        assert approval["tool"] == f"mcp__{sid}__del_file"
        conv_id = events[0]["conversation_id"]
        action_id = approval["action_id"]

        assert c.delete(f"/ai/mcp/servers/{sid}").status_code == 204
        from zhishi.domain.models import AIPendingAction
        with c.app.state.session_factory() as db:
            assert db.get(AIPendingAction, action_id).status == "expired"

        r = c.post(f"/ai/actions/{action_id}/approve")
        assert r.status_code == 404, "expired 旧卡不得再被批准"

        r = c.post(f"/ai/conversations/{conv_id}/resume/stream")
        assert r.status_code == 400
        body = r.json()
        assert body.get("consumed") is True, f"expired 批次 resume 不得回填: {body}"
        assert "过期" in body.get("message", "")


# ---- re #072：approve 后（confirmed 未消费）改服务器配置/删除重建，旧卡不得续命 ----

def _chat_and_approve(c, ai_route, sid: str) -> tuple[int, int]:
    """发起一次会触发 MCP confirm 审批的对话并 approve，返回 (conv_id, action_id)。"""
    import json as _json
    from pydantic_ai.models.function import DeltaToolCall, FunctionModel
    from zhishi.domain.models import AIConfig

    async def stream_del(messages, info):
        yield {0: DeltaToolCall(name=f"mcp__{sid}__del_file",
                                json_args=_json.dumps({"path": "a.txt"}),
                                tool_call_id="tc1")}

    ai_route.build_model = lambda cfg, api_key=None: FunctionModel(
        stream_function=stream_del)
    with c.app.state.session_factory() as db:
        db.add(AIConfig(name="t", provider_kind="openai_compat", model="t",
                        base_url="http://x", enabled=True)); db.commit()

    events = parse_sse(c.post("/ai/chat/stream", json={"message": "删掉文件"}).text)
    approval = next(e for e in events if e["type"] == "tool_approval_requested")
    conv_id, action_id = events[0]["conversation_id"], approval["action_id"]
    assert c.post(f"/ai/actions/{action_id}/approve").status_code == 200
    return conv_id, action_id


def _counting_del_server(calls: dict):
    """带执行计数的 in-process MCP 服务器：B 的工具执行次数必须可断言为 0。"""
    from mcp.server.mcpserver import MCPServer
    from mcp.types import ToolAnnotations
    server = MCPServer(name="tools")

    def del_file(path: str) -> str:
        """删除文件"""
        calls["n"] += 1
        return f"deleted {path}"

    server.add_tool(del_file, name="del_file", description="删除文件")
    return server


def test_put_change_after_approve_invalidates_confirmed_card(tmp_path, monkeypatch):
    """re #072 确定性时序（PUT）：approve 得 confirmed（未 resume）→ PUT 改连接字段 →
    旧卡必须被作废：resume 400 拒绝、B 的同名工具执行计数为 0。"""
    calls = {"n": 0}
    _patch_build_client(monkeypatch, _counting_del_server(calls))

    with TestClient(create_app(data_dir=tmp_path)) as c:
        import zhishi.server.routes.ai as ai_route
        sid = _create_server(c, "srv")
        conv_id, action_id = _chat_and_approve(c, ai_route, sid)

        assert c.put(f"/ai/mcp/servers/{sid}",
                     json={"url": "http://other-host:1234/mcp"}).status_code == 200
        from zhishi.domain.models import AIPendingAction
        with c.app.state.session_factory() as db:
            assert db.get(AIPendingAction, action_id).status == "expired", (
                "未消费 confirmed 在 PUT 连接字段变更后必须作废")

        r = c.post(f"/ai/conversations/{conv_id}/resume/stream")
        assert r.status_code == 400, "confirmed 被作废后 resume 必须整批拒绝"
        assert calls["n"] == 0, "旧卡不得借 tool_call_approved 对新服务器执行工具"


def test_delete_recreate_after_approve_invalidates_confirmed_card(tmp_path, monkeypatch):
    """re #072 确定性时序（DELETE+复用 sid）：approve → DELETE A → 新建 B 复用同 sid →
    旧 confirmed 卡作废、resume 400、B 的工具执行计数为 0、B 的工具 classify=confirm。"""
    calls = {"n": 0}
    _patch_build_client(monkeypatch, _counting_del_server(calls))

    with TestClient(create_app(data_dir=tmp_path)) as c:
        import zhishi.server.routes.ai as ai_route
        sid = _create_server(c, "srv")
        conv_id, action_id = _chat_and_approve(c, ai_route, sid)

        assert c.delete(f"/ai/mcp/servers/{sid}").status_code == 204
        assert sid == _create_server(c, "srv-b"), "前置失效：rowid 未复用"
        from zhishi.domain.models import AIPendingAction
        with c.app.state.session_factory() as db:
            assert db.get(AIPendingAction, action_id).status == "expired"
        assert _classify_mcp(c, f"mcp__{sid}__del_file") == "confirm", (
            "B 不得沿用 A 的 grant")

        r = c.post(f"/ai/conversations/{conv_id}/resume/stream")
        assert r.status_code == 400
        assert calls["n"] == 0
