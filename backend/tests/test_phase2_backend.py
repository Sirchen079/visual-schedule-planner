"""通知中心 + AI 会话管理 + 看板手动排序（第二阶段后端）。"""
from datetime import datetime, timedelta


# ---- 通知中心 ----

def _make_triggered_task(client):
    now = datetime.now()
    in_30 = now + timedelta(minutes=30)
    resp = client.post(
        "/tasks",
        json={
            "title": "半小时后开会",
            "due_date": in_30.isoformat(),
            "due_time": in_30.strftime("%H:%M"),
            "remind_offsets": [60],
        },
    )
    assert resp.status_code == 201
    return resp.json()


def test_triggered_reminder_logged_to_notification_center(client):
    _make_triggered_task(client)
    # 第一次轮询：触发落库
    client.get("/reminders/due")
    body = client.get("/notifications").json()
    hits = [n for n in body if n["title"] == "半小时后开会"]
    assert len(hits) == 1
    assert hits[0]["read_at"] is None
    assert "截止" in hits[0]["body"]

    # 再次轮询：幂等不重复
    client.get("/reminders/due")
    body = client.get("/notifications").json()
    assert len([n for n in body if n["title"] == "半小时后开会"]) == 1


def test_notification_read_flow(client):
    _make_triggered_task(client)
    client.get("/reminders/due")
    assert client.get("/notifications/unread-count").json()["unread"] >= 1

    note = client.get("/notifications").json()[0]
    read = client.post(f"/notifications/{note['id']}/read").json()
    assert read["read_at"] is not None

    # 全部已读
    resp = client.post("/notifications/read-all")
    assert resp.status_code == 200
    assert client.get("/notifications/unread-count").json()["unread"] == 0


def test_mark_read_missing_notification_404(client):
    assert client.post("/notifications/9999/read").status_code == 404


# ---- AI 会话删除/重命名 ----

def _make_conversation(client, db_session):
    from app.models import AIConversation, AIMessage

    conv = AIConversation(title="原始标题")
    db_session.add(conv)
    db_session.commit()
    db_session.refresh(conv)
    db_session.add(AIMessage(conversation_id=conv.id, role="user", content="你好"))
    db_session.commit()
    return conv


def test_rename_conversation(client, db_session):
    conv = _make_conversation(client, db_session)
    resp = client.patch(f"/ai/conversations/{conv.id}", json={"title": "新标题"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "新标题"
    assert resp.json()["message_count"] == 1


def test_delete_conversation(client, db_session):
    from app.models import AIMessage

    conv = _make_conversation(client, db_session)
    resp = client.delete(f"/ai/conversations/{conv.id}")
    assert resp.status_code == 204
    assert client.get(f"/ai/conversations/{conv.id}").status_code == 404
    assert db_session.query(AIMessage).filter_by(conversation_id=conv.id).count() == 0


def test_rename_missing_conversation_404(client):
    assert client.patch("/ai/conversations/9999", json={"title": "x"}).status_code == 404


# ---- 看板手动排序 ----

def test_sort_order_controls_default_listing(client):
    a = client.post("/tasks", json={"title": "A"}).json()
    b = client.post("/tasks", json={"title": "B"}).json()
    # 默认（sort_order 均为 0）：创建时间倒序，B 在前
    titles = [t["title"] for t in client.get("/tasks").json()]
    assert titles[:2] == ["B", "A"]

    # 把 A 的 sort_order 调小 → A 排到最前
    client.put(f"/tasks/{a['id']}", json={"sort_order": -1})
    titles = [t["title"] for t in client.get("/tasks").json()]
    assert titles[0] == "A"
    # B 未受影响
    assert titles[1] == "B"


def test_sort_order_roundtrip_in_response(client):
    task = client.post("/tasks", json={"title": "权重任务"}).json()
    assert task["sort_order"] == 0
    updated = client.put(f"/tasks/{task['id']}", json={"sort_order": 2.5}).json()
    assert updated["sort_order"] == 2.5
