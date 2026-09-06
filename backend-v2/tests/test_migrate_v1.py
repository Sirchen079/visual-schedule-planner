# tests/test_migrate_v1.py
"""旧版 v1 → v2 数据迁移：源库只读（绝不写旧库）、逐域映射、dry-run、附件拷贝解析。
测试全程在 tmp 构造旧库副本，绝不触碰真实 E:\\知时\\data。"""
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest
from sqlalchemy import select

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import migrate_v1

from zhishi.domain.models import (
    AppSetting,
    Goal,
    Habit,
    HabitLog,
    JournalEntry,
    KeyResult,
    LibraryFile,
    Subtask,
    Task,
    TaskScheduleEntry,
    TimeLog,
)
from zhishi.infra.database import create_all, make_engine, make_session_factory

# 旧库 schema（列名对齐真实 v1 app.db，取迁移所需列）
OLD_SCHEMA = """
CREATE TABLE tasks (
  id INTEGER PRIMARY KEY, title VARCHAR(200), notes TEXT, due_date DATETIME,
  priority VARCHAR(10), status VARCHAR(20), progress INTEGER, start_date DATETIME,
  end_date DATETIME, created_at DATETIME, updated_at DATETIME, deleted_at DATETIME,
  completed_at DATETIME, due_time VARCHAR(5), remind_offsets TEXT,
  recur_rule VARCHAR(20), recur_interval INTEGER, sort_order FLOAT, estimated_minutes INTEGER);
CREATE TABLE subtasks (
  id INTEGER PRIMARY KEY, task_id INTEGER, title VARCHAR(200), done BOOLEAN,
  completed_at DATETIME, created_at DATETIME, estimated_minutes INTEGER);
CREATE TABLE tags (id INTEGER PRIMARY KEY, name VARCHAR(50), color VARCHAR(20));
CREATE TABLE task_tag (task_id INTEGER, tag_id INTEGER);
CREATE TABLE task_schedule_entries (
  id INTEGER PRIMARY KEY, task_id INTEGER, date DATE, source VARCHAR(20), note TEXT,
  created_at DATETIME, updated_at DATETIME, start_time VARCHAR(5), end_time VARCHAR(5));
CREATE TABLE files (
  id INTEGER PRIMARY KEY, original_name VARCHAR(255), storage_path VARCHAR(500),
  size INTEGER, mime_type VARCHAR(100), notes TEXT, source_url VARCHAR(1000),
  resource_type VARCHAR(30), uploaded_at DATETIME, deleted_at DATETIME);
CREATE TABLE task_file (task_id INTEGER, file_id INTEGER);
CREATE TABLE habits (
  id INTEGER PRIMARY KEY, name VARCHAR(100), notes TEXT, period VARCHAR(10),
  target_count INTEGER, color VARCHAR(20), sort_order FLOAT, created_at DATETIME,
  deleted_at DATETIME);
CREATE TABLE habit_logs (id INTEGER PRIMARY KEY, habit_id INTEGER, date DATE, count INTEGER);
CREATE TABLE goals (
  id INTEGER PRIMARY KEY, title VARCHAR(200), notes TEXT, status VARCHAR(20),
  start_date DATE, end_date DATE, sort_order FLOAT, created_at DATETIME, deleted_at DATETIME);
CREATE TABLE key_results (
  id INTEGER PRIMARY KEY, goal_id INTEGER, title VARCHAR(200), kind VARCHAR(20),
  target_value FLOAT, current_value FLOAT, unit VARCHAR(20), link TEXT, created_at DATETIME);
CREATE TABLE journal_entries (
  id INTEGER PRIMARY KEY, date DATE, content TEXT, mood VARCHAR(20),
  created_at DATETIME, updated_at DATETIME);
CREATE TABLE time_logs (
  id INTEGER PRIMARY KEY, task_id INTEGER, task_title VARCHAR(200), kind VARCHAR(20),
  started_at DATETIME, ended_at DATETIME, minutes INTEGER, created_at DATETIME);
CREATE TABLE app_settings (key VARCHAR(64), value TEXT, updated_at DATETIME);
"""


@pytest.fixture
def old_data(tmp_path):
    """tmp 构造旧版数据目录 v1data/（app.db + files/hello.txt）。返回 (old_db, v1data)。"""
    v1data = tmp_path / "v1data"
    (v1data / "files").mkdir(parents=True)
    (v1data / "files" / "hello.txt").write_text("附件正文内容", encoding="utf-8")
    con = sqlite3.connect(v1data / "app.db")
    con.executescript(OLD_SCHEMA)
    con.execute(
        "INSERT INTO tasks VALUES (1,'写周报','notes1','2026-09-01 10:00:00','high','todo',5,"
        "NULL,NULL,'2026-08-30 08:00:00','2026-08-30 08:00:00',NULL,NULL,'09:00','[0,30,1440]',"
        "'weekly',1,1.0,30)")
    con.execute(
        "INSERT INTO tasks VALUES (2,'已删任务','',NULL,'low','done',100,"
        "'2026-08-01 08:00:00',NULL,'2026-08-01 08:00:00','2026-08-02 08:00:00',"
        "'2026-08-03 08:00:00','2026-08-02 09:00:00',NULL,'not-json','none',1,2.0,NULL)")
    con.execute("INSERT INTO tags VALUES (1,'工作','#ff0000')")
    con.execute("INSERT INTO tags VALUES (2,'深呼吸','#00ff00')")
    con.execute("INSERT INTO task_tag VALUES (1,1)")
    con.execute("INSERT INTO task_tag VALUES (1,2)")
    con.execute(
        "INSERT INTO subtasks VALUES (1,1,'列提纲',1,'2026-08-31 09:00:00',"
        "'2026-08-30 08:00:00',10)")
    con.execute(
        "INSERT INTO task_schedule_entries VALUES (1,1,'2026-09-01','manual','n',"
        "'2026-08-30 08:00:00','2026-08-30 08:00:00','09:00','10:00')")
    con.execute(
        "INSERT INTO files VALUES (1,'hello.txt','files/hello.txt',18,'text/plain','备注',"
        "NULL,'file','2026-08-30 08:00:00',NULL)")
    con.execute(
        "INSERT INTO files VALUES (2,'某链接','https://example.com/a',0,'text/uri-list','',"
        "'https://example.com/a','link','2026-08-30 08:00:00',NULL)")
    con.execute("INSERT INTO task_file VALUES (1,1)")
    con.execute(
        "INSERT INTO habits VALUES (1,'晨间散步','','daily',1,'#22c55e',0,"
        "'2026-08-01 08:00:00',NULL)")
    con.execute("INSERT INTO habit_logs VALUES (1,1,'2026-09-01',1)")
    con.execute("INSERT INTO habit_logs VALUES (2,1,'2026-09-02',2)")
    con.execute(
        "INSERT INTO goals VALUES (1,'学会 Rust','','active','2026-08-01','2026-12-31',0,"
        "'2026-08-01 08:00:00',NULL)")
    con.execute(
        "INSERT INTO key_results VALUES (1,1,'读完入门书','manual',100,20,'页','',"
        "'2026-08-01 08:00:00')")
    con.execute(
        "INSERT INTO journal_entries VALUES (1,'2026-09-01','今天不错','good',"
        "'2026-09-01 21:00:00','2026-09-01 21:00:00')")
    con.execute(
        "INSERT INTO time_logs VALUES (1,1,'写周报','focus','2026-09-01 10:00:00',"
        "'2026-09-01 10:25:00',25,'2026-09-01 10:25:00')")
    con.execute("INSERT INTO app_settings VALUES ('assistant_mode','agent',NULL)")
    con.execute("INSERT INTO app_settings VALUES ('working_hours_start','08:30',NULL)")
    con.execute("INSERT INTO app_settings VALUES ('tz_normalized_v1','1',NULL)")
    con.commit()
    con.close()
    return v1data / "app.db", v1data


def _snapshot(base: Path):
    return (hashlib.sha256((base / "app.db").read_bytes()).hexdigest(),
            sorted(p.relative_to(base).as_posix() for p in base.rglob("*")))


def _open_new(new_dir: Path):
    engine = make_engine(new_dir / "backend.db")
    create_all(engine)
    session = make_session_factory(engine)()
    return engine, session


def test_migrate_full(old_data, tmp_path):
    old_db, v1data = old_data
    before = _snapshot(v1data)
    new_dir = tmp_path / "v2"

    report = migrate_v1.migrate(old_db, new_dir, attachments=v1data)

    # 旧库内容与目录文件清单零改动（只读校验）
    assert _snapshot(v1data) == before

    dom = report["domains"]
    assert dom["tasks"]["migrated"] == 2
    assert dom["subtasks"]["migrated"] == 1
    assert dom["schedule_entries"]["migrated"] == 1
    assert dom["habits"]["migrated"] == 1
    assert dom["habit_logs"]["migrated"] == 2
    assert dom["goals"]["migrated"] == 1
    assert dom["key_results"]["migrated"] == 1
    assert dom["journal"]["migrated"] == 1
    assert dom["time_logs"]["migrated"] == 1
    assert dom["files"]["migrated"] == 2      # 文件 + 链接
    assert dom["files"]["copied"] == 1        # 仅文件实体拷贝
    assert dom["files"]["parsed"] == 1
    assert dom["task_file_links"]["migrated"] == 1
    assert dom["settings"]["migrated"] == 2   # 白名单 2 键
    assert dom["settings"]["skipped"] == 1    # tz_normalized_v1 不在白名单
    # 新 id 映射表
    assert set(report["id_map"]["tasks"]) == {1, 2}
    assert set(report["id_map"]["habits"]) == {1}
    assert set(report["id_map"]["goals"]) == {1}
    assert set(report["id_map"]["files"]) == {1, 2}

    # 新库可查且语义正确
    engine, session = _open_new(new_dir)
    t = session.scalar(select(Task).where(Task.title == "写周报"))
    assert t.priority == "high" and t.remind_offsets == "[0,30,1440]"
    assert t.recur_rule == "weekly" and t.recur_rrule is None
    assert t.due_time == "09:00" and t.estimated_minutes == 30
    assert sorted(tag.name for tag in t.tags) == ["工作", "深呼吸"]
    t2 = session.scalar(select(Task).where(Task.title == "已删任务"))
    assert t2.remind_offsets == "[]" and t2.deleted_at is not None
    assert session.scalar(select(Subtask).where(
        Subtask.task_id == t.id)).title == "列提纲"
    assert session.scalar(select(TaskScheduleEntry).where(
        TaskScheduleEntry.task_id == t.id)).start_time == "09:00"
    assert session.scalar(select(TimeLog).where(TimeLog.task_id == t.id)).minutes == 25
    h = session.scalar(select(Habit).where(Habit.name == "晨间散步"))
    logs = list(session.scalars(select(HabitLog).where(HabitLog.habit_id == h.id)))
    assert sorted(l.count for l in logs) == [1, 2]
    g = session.scalar(select(Goal).where(Goal.title == "学会 Rust"))
    assert session.scalar(select(KeyResult).where(KeyResult.goal_id == g.id)).target_value == 100
    assert session.scalar(select(JournalEntry)).content == "今天不错"
    keys = {k for k, in session.execute(select(AppSetting.key))}
    assert keys == {"assistant_mode", "working_hours_start"}
    assert session.scalar(select(AppSetting).where(
        AppSetting.key == "working_hours_start")).value == "08:30"
    # 附件：拷贝到 v2/attachments 并回填解析
    f = session.scalar(select(LibraryFile).where(LibraryFile.original_name == "hello.txt"))
    assert f.parse_status == "parsed" and "附件正文内容" in f.extracted_text
    assert (new_dir / f.storage_path).read_text(encoding="utf-8") == "附件正文内容"
    link = session.scalar(select(LibraryFile).where(LibraryFile.resource_type == "link"))
    assert link.source_url == "https://example.com/a"
    session.close()
    engine.dispose()


def test_dry_run_writes_nothing(old_data, tmp_path):
    old_db, v1data = old_data
    before = _snapshot(v1data)
    new_dir = tmp_path / "v2"

    report = migrate_v1.migrate(old_db, new_dir, dry_run=True)

    assert report["dry_run"] is True
    assert report["domains"]["tasks"]["migrated"] == 2
    assert report["domains"]["files"]["migrated"] == 2
    assert not new_dir.exists()            # 不建新库
    assert _snapshot(v1data) == before     # 不碰旧库


def test_missing_table_skipped(old_data, tmp_path):
    old_db, _v1data = old_data
    con = sqlite3.connect(old_db)
    con.execute("DROP TABLE goals")
    con.execute("DROP TABLE key_results")
    con.commit()
    con.close()

    report = migrate_v1.migrate(old_db, tmp_path / "v2")

    for name in ("goals", "key_results"):
        assert report["domains"][name]["migrated"] == 0
        assert "旧库无该表" in report["domains"][name]["note"]


def test_without_attachments_records_only(old_data, tmp_path):
    old_db, _v1data = old_data
    report = migrate_v1.migrate(old_db, tmp_path / "v2")
    dom = report["domains"]["files"]
    assert dom["migrated"] == 2 and dom["copied"] == 0 and dom["parsed"] == 0


def test_cli_main_reports_json(old_data, tmp_path, capsys):
    old_db, v1data = old_data
    rc = migrate_v1.main(["--from", str(old_db), "--data-dir", str(tmp_path / "v2"),
                          "--attachments", str(v1data)])
    out = capsys.readouterr().out
    assert rc == 0
    parsed = json.loads(out)
    assert parsed["domains"]["tasks"]["migrated"] == 2
    assert "id_map" not in parsed  # CLI 报告不含大块 id 映射
