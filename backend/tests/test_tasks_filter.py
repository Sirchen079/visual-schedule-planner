"""任务列表查询参数：q / status / priority / tag / due 范围 / 排序。"""
from datetime import datetime, timedelta


def _seed(client):
    now = datetime.now()
    a = client.post(
        "/tasks",
        json={
            "title": "写季度报告",
            "notes": "需要数据",
            "priority": "高",
            "due_date": (now + timedelta(days=1)).isoformat(),
            "tags": ["工作"],
        },
    ).json()
    b = client.post(
        "/tasks",
        json={
            "title": "买牛奶",
            "priority": "低",
            "due_date": (now + timedelta(days=10)).isoformat(),
            "tags": ["生活"],
        },
    ).json()
    c = client.post("/tasks", json={"title": "周报模板", "status": "完成"}).json()
    return a, b, c


def test_filter_by_q_matches_title_and_notes(client):
    _seed(client)
    titles = [t["title"] for t in client.get("/tasks?q=报告").json()]
    assert "写季度报告" in titles
    assert "买牛奶" not in titles
    # 备注也参与搜索
    titles = [t["title"] for t in client.get("/tasks?q=数据").json()]
    assert titles == ["写季度报告"]


def test_filter_by_status_and_priority(client):
    _seed(client)
    done = client.get("/tasks?status=完成").json()
    assert [t["title"] for t in done] == ["周报模板"]
    high = client.get("/tasks?priority=高").json()
    assert [t["title"] for t in high] == ["写季度报告"]


def test_filter_by_tag(client):
    _seed(client)
    life = client.get("/tasks?tag=生活").json()
    assert [t["title"] for t in life] == ["买牛奶"]


def test_filter_by_due_range(client):
    _seed(client)
    now = datetime.now()
    before = (now + timedelta(days=5)).isoformat()
    after = (now - timedelta(days=1)).isoformat()
    items = client.get(f"/tasks?due_before={before}&due_after={after}").json()
    titles = [t["title"] for t in items]
    assert "写季度报告" in titles
    assert "买牛奶" not in titles  # 10 天后超出 due_before
    assert "周报模板" not in titles  # 无 due_date 不参与


def test_sort_by_due_date_asc(client):
    _seed(client)
    items = client.get("/tasks?sort=due_date&order=asc").json()
    dues = [t["due_date"] for t in items if t["due_date"]]
    assert dues == sorted(dues)


def test_no_params_keeps_legacy_behavior(client):
    _seed(client)
    items = client.get("/tasks").json()
    assert len(items) == 3
    created = [t["created_at"] for t in items]
    assert created == sorted(created, reverse=True)
