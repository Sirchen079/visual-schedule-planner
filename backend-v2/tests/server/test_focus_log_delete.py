# tests/server/test_focus_log_delete.py
"""re k3#048 残留清理诉求：新增 DELETE /api/focus/logs/{log_id}——仅已结束的
记录可删（204）；运行中的计时不可直接删（409，先停后删）；不存在 404。"""
from fastapi.testclient import TestClient
from zhishi.server.app import create_app


def test_delete_finished_log_204_then_404(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        from zhishi.domain.focus import service as focus_service
        from zhishi.domain.focus.schemas import TimerStart
        with c.app.state.session_factory() as db:
            focus_service.start_timer(db, TimerStart(task_title="旧探针"))
            log = focus_service.stop_timer(db, None)
            assert log is not None and log.ended_at is not None
            lid = log.id
        assert c.delete(f"/api/focus/logs/{lid}").status_code == 204
        assert c.get("/api/focus/logs").json() == []
        assert c.delete(f"/api/focus/logs/{lid}").status_code == 404   # 重复删除


def test_delete_running_log_conflict_409(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        run = c.post("/api/focus/start", json={"task_title": "进行中"}).json()
        r = c.delete(f"/api/focus/logs/{run['id']}")
        assert r.status_code == 409
        assert any(l["id"] == run["id"] for l in c.get("/api/focus/logs").json()), \
            "运行中的记录被误删"
