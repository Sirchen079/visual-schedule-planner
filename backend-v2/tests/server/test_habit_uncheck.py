# tests/server/test_habit_uncheck.py
"""re #B3：POST /api/habits/{id}/uncheck 的 body 契约与实现对齐。
date 缺省=今天（与 check_in 的 day=None 语义一致），空 body 不再 422；
openapi schema 如实标注 date 可选。"""
from fastapi.testclient import TestClient
from zhishi.server.app import create_app


def test_uncheck_without_body_defaults_to_today(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        h = c.post("/api/habits", json={"name": "跑步"}).json()["id"]
        c.post(f"/api/habits/{h}/check-in", json={})       # 今天打卡两笔
        c.post(f"/api/habits/{h}/check-in", json={})
        r = c.post(f"/api/habits/{h}/uncheck")             # 空 body：此前 422
        assert r.status_code == 200 and r.json() == {"ok": True}
        logs = c.get(f"/api/habits/{h}/logs").json()
        assert len(logs) == 1 and logs[0]["count"] == 1    # 撤销一笔，剩余 1


def test_uncheck_with_explicit_date_still_works(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        h = c.post("/api/habits", json={"name": "跑步"}).json()["id"]
        c.post(f"/api/habits/{h}/check-in", json={"date": "2026-09-01"})
        r = c.post(f"/api/habits/{h}/uncheck", json={"date": "2026-09-01"})
        assert r.status_code == 200 and r.json() == {"ok": True}
        # count 归 0 后日志行删除
        assert c.get(f"/api/habits/{h}/logs").json() == []
        # 非法日期仍 422
        assert c.post(f"/api/habits/{h}/uncheck", json={"date": "nope"}).status_code == 422


def test_uncheck_openapi_marks_date_optional(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        op = c.app.openapi()["paths"]["/api/habits/{habit_id}/uncheck"]["post"]
        schema = op["requestBody"]["content"]["application/json"]["schema"]
        required = schema.get("required", [])
        assert "date" not in required
