"""已有数据库的幂等结构升级：启动时为旧表补充缺失列。"""
import sqlite3

OLD_MCP_SCHEMA = """
CREATE TABLE mcp_servers (
    id INTEGER NOT NULL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    transport VARCHAR(10) NOT NULL,
    command VARCHAR(500),
    args_json TEXT NOT NULL,
    env_json TEXT NOT NULL,
    url VARCHAR(1000),
    headers_json TEXT NOT NULL,
    timeout_sec INTEGER NOT NULL,
    enabled BOOLEAN NOT NULL,
    auto_approve_readonly BOOLEAN NOT NULL,
    last_status VARCHAR(10) NOT NULL,
    last_error TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    UNIQUE (name)
);
INSERT INTO mcp_servers (name, transport, args_json, env_json, headers_json,
                         timeout_sec, enabled, auto_approve_readonly, last_status)
VALUES ('旧库服务器', 'http', '[]', '{}', '{}', 30, 0, 0, 'untested');
"""


def test_existing_db_gets_trusted_column(tmp_path):
    data_dir = tmp_path / "d"
    (data_dir / "v2").mkdir(parents=True)
    db = data_dir / "v2" / "backend.db"
    con = sqlite3.connect(db)
    con.executescript(OLD_MCP_SCHEMA)
    con.commit()
    con.close()

    from fastapi.testclient import TestClient
    from zhishi.server.app import create_app
    with TestClient(create_app(data_dir=data_dir)) as c:
        r = c.get("/ai/mcp/servers")
        assert r.status_code == 200, f"旧库未迁移: {r.status_code} {r.text[:200]}"
        rows = r.json()
        assert any(s["name"] == "旧库服务器" for s in rows)   # 旧数据完好
    # 二次启动幂等
    with TestClient(create_app(data_dir=data_dir)) as c:
        assert c.get("/ai/mcp/servers").status_code == 200


OLD_EVENTS_SCHEMA = """
CREATE TABLE events (
    id INTEGER NOT NULL PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    date DATE NOT NULL,
    start_time VARCHAR(5),
    end_time VARCHAR(5),
    location VARCHAR(200) NOT NULL,
    category VARCHAR(30) NOT NULL,
    recur_rrule TEXT,
    notes TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
);
INSERT INTO events (title, date, location, category, notes)
VALUES ('旧库课程', '2026-09-07', 'A101', 'course', '');
"""


def test_existing_db_gets_repeat_note_column(tmp_path):
    """events 表补 repeat_note 列——存量课表库启动自动迁移，
    旧行该列为 NULL，expand 视图照常可用（repeat_note 可空）。"""
    data_dir = tmp_path / "d"
    (data_dir / "v2").mkdir(parents=True)
    con = sqlite3.connect(data_dir / "v2" / "backend.db")
    con.executescript(OLD_EVENTS_SCHEMA)
    con.commit()
    con.close()

    from fastapi.testclient import TestClient
    from zhishi.server.app import create_app
    with TestClient(create_app(data_dir=data_dir)) as c:
        expand = c.get("/api/schedule/events/expand",
                       params={"start": "2026-09-07", "end": "2026-09-07"})
        assert expand.status_code == 200, f"旧库未迁移: {expand.status_code}"
        rows = expand.json()
        assert any(e["title"] == "旧库课程" for e in rows)   # 旧数据完好
        assert all(e["repeat_note"] is None for e in rows)   # 旧行补列为 NULL
    # 二次启动幂等
    with TestClient(create_app(data_dir=data_dir)) as c:
        assert c.get("/api/schedule/events/expand",
                     params={"start": "2026-09-07", "end": "2026-09-07"}).status_code == 200
