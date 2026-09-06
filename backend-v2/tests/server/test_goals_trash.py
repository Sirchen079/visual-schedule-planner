# tests/server/test_goals_trash.py
"""re #B2：goals 软删语义对齐 tasks 回收站模式。
- GET /api/goals/trash 列已删（带 key_results 与 deleted_at）
- POST /api/goals/{id}/restore 恢复；DELETE /api/goals/{id}/purge 硬删（级联 KR）
- purge 仅对回收站中的目标放行（未软删 → 409）
- include_archived 改名 include_deleted（旧名 alias 兼容），返回项带 deleted_at，
  已删目标的 status 保持原值透出（幽灵行显式可辨）。"""
from fastapi.testclient import TestClient
from zhishi.server.app import create_app


def _mk_goal(c, title: str) -> int:
    return c.post("/api/goals", json={"title": title}).json()["id"]


def test_include_deleted_returns_only_deleted_with_deleted_at(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        keep = _mk_goal(c, "留存目标")
        gone = _mk_goal(c, "删除目标")
        assert c.delete(f"/api/goals/{gone}").status_code == 204

        live = {g["id"]: g for g in c.get("/api/goals").json()}
        assert keep in live and gone not in live

        # 新参数名：含已删
        both = {g["id"]: g for g in c.get("/api/goals", params={"include_deleted": True}).json()}
        assert set(both) == {keep, gone}
        assert both[gone]["deleted_at"] is not None          # 已删项透出 deleted_at
        assert both[gone]["status"] == "active"              # status 保持原值（幽灵行可辨）
        assert both[keep]["deleted_at"] is None

        # 旧参数名 alias 兼容：行为一致
        legacy = c.get("/api/goals", params={"include_archived": True})
        assert legacy.status_code == 200
        assert {g["id"] for g in legacy.json()} == {keep, gone}


def test_trash_restore_purge_cycle(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        a = _mk_goal(c, "目标A")
        b = _mk_goal(c, "目标B")
        c.post(f"/api/goals/{a}/key-results", json={"title": "KR-A"})
        c.post(f"/api/goals/{b}/key-results", json={"title": "KR-B"})
        c.delete(f"/api/goals/{a}")
        c.delete(f"/api/goals/{b}")

        trash = c.get("/api/goals/trash").json()
        assert {g["id"] for g in trash} == {a, b}
        assert all(g["deleted_at"] and len(g["key_results"]) == 1 for g in trash)

        # restore 后回到活动列表、离开回收站
        assert c.post(f"/api/goals/{a}/restore").status_code == 200
        assert {g["id"] for g in c.get("/api/goals").json()} == {a}
        assert {g["id"] for g in c.get("/api/goals/trash").json()} == {b}

        # purge 硬删 + 级联 KR
        assert c.delete(f"/api/goals/{b}/purge").status_code == 204
        assert {g["id"] for g in c.get("/api/goals", params={"include_deleted": True}).json()} == {a}
        from zhishi.domain.models import Goal, KeyResult
        with c.app.state.session_factory() as db:
            assert db.get(Goal, b) is None
            assert db.query(KeyResult).filter_by(goal_id=b).all() == []
        assert c.get(f"/api/goals/{b}").status_code == 404

        # 未软删的目标不可 purge（409），未知 id 404
        r = c.delete(f"/api/goals/{a}/purge")
        assert r.status_code == 409
        assert c.delete("/api/goals/9999/purge").status_code == 404
        assert c.post("/api/goals/9999/restore").status_code == 404
        assert c.get("/api/goals/9999").status_code == 404


def test_trash_endpoint_documented_in_openapi(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        spec = c.app.openapi()["paths"]
        assert "/api/goals/trash" in spec and "get" in spec["/api/goals/trash"]
        assert "post" in spec["/api/goals/{goal_id}/restore"]
        assert "delete" in spec["/api/goals/{goal_id}/purge"]
        params = {p["name"]: p for p in spec["/api/goals"]["get"]["parameters"]}
        assert "include_deleted" in params
        assert params["include_archived"]["deprecated"] is True
