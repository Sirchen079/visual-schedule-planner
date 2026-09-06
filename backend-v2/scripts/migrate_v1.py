# scripts/migrate_v1.py
"""知时 v1 → v2 一次性数据迁移。

用法：
  python scripts/migrate_v1.py --from <旧app.db路径> [--dry-run] \
      [--attachments <旧data目录>] [--data-dir data/v2]

铁律：源库以 sqlite 只读模式（file:...?mode=ro）打开，绝不写旧库；
AI 层数据（会话/消息/配置/报告）不迁；ID 不保序，返回新旧 id 映射表。
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from zhishi.domain.library.service import ensure_parsed, save_local_file
from zhishi.domain.models import (
    AppSetting,
    Goal,
    Habit,
    HabitLog,
    JournalEntry,
    KeyResult,
    LibraryFile,
    Subtask,
    Tag,
    Task,
    TaskScheduleEntry,
    TimeLog,
    task_file,
)
from zhishi.infra.database import create_all, make_engine, make_session_factory

# app_settings 只迁这些键（v1 其余键属于旧前端行为，v2 不消费）
_SETTINGS_KEYS = {"assistant_mode", "agent_autonomy"}
_SETTINGS_PREFIXES = ("working_hours_",)
_RECUR_RULES = {"none", "daily", "weekdays", "weekly", "monthly"}


def _domain() -> dict:
    return {"migrated": 0, "skipped": 0, "failed": [], "note": ""}


def _fail(dom: dict, row_id, reason: Exception | str) -> None:
    dom["failed"].append({"id": row_id, "reason": str(reason)[:300]})


def _parse_dt(value) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).replace("T", " ").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None  # 脏值按空处理，不阻塞迁移


def _parse_date(value) -> date | None:
    dt = _parse_dt(value)
    return dt.date() if dt else None


def _connect_ro(old_db: Path) -> sqlite3.Connection:
    """只读连接。URI 用 posix 风格路径（Windows 盘符/中文路径均可）。"""
    uri = f"file:{old_db.resolve().as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _rows(cur: sqlite3.Cursor, table: str, columns: list[str], dom: dict) -> list[dict] | None:
    """读全表（显式列）。旧库无该表 → 返回 None 并在报告记 note。
    表名/列名虽来自 sqlite_master 内省而非外部输入，仍先经 _IDENT_RE 严格校验
    （仅字母数字下划线、无引号无空白，标识符无法参数绑定）再经 join 构造查询。"""
    if cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                   (table,)).fetchone() is None:
        dom["note"] = "旧库无该表，跳过"
        return None
    if not _IDENT_RE.fullmatch(table) or any(
            not _IDENT_RE.fullmatch(c) for c in columns):
        raise ValueError(f"旧库出现非法标识符，拒绝读取：{table} / {columns}")
    cols = ", ".join(columns)
    cur.row_factory = sqlite3.Row
    sql = " ".join(("SELECT", cols, "FROM", table))
    return [dict(r) for r in cur.execute(sql)]


def _count(cur: sqlite3.Cursor, table: str) -> int:
    if cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                   (table,)).fetchone() is None:
        return 0
    if not _IDENT_RE.fullmatch(table):
        raise ValueError(f"旧库出现非法表名，拒绝读取：{table}")
    sql = " ".join(("SELECT COUNT(*) FROM", table))
    return cur.execute(sql).fetchone()[0]


def _resolve_source(attachments: Path, storage_path: str) -> Path | None:
    """旧 storage_path 兼容两种形态：'files/x'（相对旧 data/）与
    'data/files/x'（相对旧安装根，即 attachments 的父目录）。"""
    rel = storage_path.replace("\\", "/").lstrip("/")
    for base in (attachments, attachments.parent):
        cand = base / rel
        if cand.is_file():
            return cand
    return None


def migrate(old_db: Path, data_dir: Path, *, dry_run: bool = False,
            attachments: Path | None = None) -> dict:
    """执行迁移。返回 {"domains": {...}, "id_map": {...}, "dry_run": bool}。"""
    old_db, data_dir = Path(old_db), Path(data_dir)
    if not old_db.is_file():
        raise FileNotFoundError(f"旧库不存在：{old_db}")
    if not dry_run and old_db.resolve() == (data_dir / "backend.db").resolve():
        raise ValueError("目标新库与源库相同，拒绝执行")

    report: dict = {"dry_run": dry_run, "domains": {}, "id_map": {}}
    dom = report["domains"]
    for name in ("tasks", "subtasks", "schedule_entries", "habits", "habit_logs",
                 "goals", "key_results", "journal", "time_logs", "files",
                 "task_file_links", "settings"):
        dom[name] = _domain()
    dom["files"]["copied"] = 0   # 实体拷贝数 / 解析回填成功数（仅 files 域有）
    dom["files"]["parsed"] = 0

    con = _connect_ro(old_db)
    try:
        cur = con.cursor()

        if dry_run:  # 只报告不写：按行数估算
            for name, table in (("tasks", "tasks"), ("subtasks", "subtasks"),
                                ("schedule_entries", "task_schedule_entries"),
                                ("habits", "habits"), ("habit_logs", "habit_logs"),
                                ("goals", "goals"), ("key_results", "key_results"),
                                ("journal", "journal_entries"),
                                ("time_logs", "time_logs"), ("files", "files")):
                dom[name]["migrated"] = _count(cur, table)
            dom["task_file_links"]["migrated"] = _count(cur, "task_file")
            settings = _rows(cur, "app_settings", ["key", "value"], dom["settings"]) or []
            for row in settings:
                if row["key"] in _SETTINGS_KEYS or row["key"].startswith(_SETTINGS_PREFIXES):
                    dom["settings"]["migrated"] += 1
                else:
                    dom["settings"]["skipped"] += 1
            return report

        # ---- 真实迁移：新库用 zhishi.infra.database 的引擎构造 ----
        engine = make_engine(data_dir / "backend.db")
        create_all(engine)
        session = make_session_factory(engine)()
        storage_root = data_dir / "attachments"
        id_map = report["id_map"] = {"tasks": {}, "habits": {}, "goals": {}, "files": {}}

        def get_tag(name: str) -> Tag:
            row = session.scalar(select(Tag).where(Tag.name == name))
            if row is None:
                row = Tag(name=name)
                session.add(row)
                session.flush()
            return row

        def commit_row(row, dom_key, old_id, new_key=None) -> None:
            session.add(row)
            session.commit()
            dom[dom_key]["migrated"] += 1
            if new_key is not None:
                id_map[new_key][old_id] = row.id

        # 1. tasks（tags 由 task_tag+tags 联查映射；recur_rrule 空着）
        rows = _rows(cur, "tasks", [
            "id", "title", "notes", "due_date", "priority", "status", "progress",
            "start_date", "created_at", "updated_at", "deleted_at", "completed_at",
            "due_time", "remind_offsets", "recur_rule", "recur_interval", "sort_order",
            "estimated_minutes"], dom["tasks"])
        tag_names_by_task: dict[int, list[str]] = {}
        tag_rows = _rows(cur, "tags", ["id", "name"], dom["tasks"])
        tt_rows = _rows(cur, "task_tag", ["task_id", "tag_id"], dom["tasks"])
        if tag_rows and tt_rows:
            names = {t["id"]: t["name"] for t in tag_rows}
            for tt in tt_rows:
                tag_names_by_task.setdefault(tt["task_id"], []).append(names.get(tt["tag_id"], ""))
        for r in rows or []:
            try:
                remind = r["remind_offsets"]
                if remind:
                    try:
                        json.loads(remind)
                    except ValueError:
                        remind = "[]"
                task = Task(
                    title=r["title"] or "未命名", notes=r["notes"] or "",
                    due_date=_parse_dt(r["due_date"]), due_time=r["due_time"],
                    remind_offsets=remind or "[]", priority=r["priority"] or "medium",
                    status=r["status"] or "todo", progress=int(r["progress"] or 0),
                    start_date=_parse_dt(r["start_date"]),
                    recur_rule=r["recur_rule"] if r["recur_rule"] in _RECUR_RULES else "none",
                    recur_interval=int(r["recur_interval"] or 1),
                    estimated_minutes=r["estimated_minutes"],
                    sort_order=float(r["sort_order"] or 0.0),
                    created_at=_parse_dt(r["created_at"]) or datetime.now(),
                    updated_at=_parse_dt(r["updated_at"]) or datetime.now(),
                    completed_at=_parse_dt(r["completed_at"]),
                    deleted_at=_parse_dt(r["deleted_at"]))
                for name in filter(None, tag_names_by_task.get(r["id"], [])):
                    tag = get_tag(name)
                    if tag not in task.tags:
                        task.tags.append(tag)
                commit_row(task, "tasks", r["id"], "tasks")
            except Exception as exc:
                session.rollback()
                _fail(dom["tasks"], r["id"], exc)

        # 2. subtasks（旧 task_id 映射，查无映射则跳过）
        rows = _rows(cur, "subtasks", ["id", "task_id", "title", "done", "completed_at",
                                       "created_at", "estimated_minutes"], dom["subtasks"])
        for r in rows or []:
            try:
                if r["task_id"] not in id_map["tasks"]:
                    dom["subtasks"]["skipped"] += 1
                    continue
                sub = Subtask(task_id=id_map["tasks"][r["task_id"]], title=r["title"] or "",
                              done=bool(r["done"]), completed_at=_parse_dt(r["completed_at"]),
                              estimated_minutes=r["estimated_minutes"],
                              created_at=_parse_dt(r["created_at"]) or datetime.now())
                session.add(sub)
                session.commit()
                dom["subtasks"]["migrated"] += 1
            except Exception as exc:
                session.rollback()
                _fail(dom["subtasks"], r["id"], exc)

        # 3. task_schedule_entries（task_id+date 唯一，重复跳过）
        rows = _rows(cur, "task_schedule_entries",
                     ["id", "task_id", "date", "source", "note", "created_at",
                      "start_time", "end_time"], dom["schedule_entries"])
        for r in rows or []:
            try:
                if r["task_id"] not in id_map["tasks"]:
                    dom["schedule_entries"]["skipped"] += 1
                    continue
                entry = TaskScheduleEntry(
                    task_id=id_map["tasks"][r["task_id"]], date=_parse_date(r["date"]),
                    start_time=r["start_time"], end_time=r["end_time"],
                    source=r["source"] or "manual", note=r["note"] or "",
                    created_at=_parse_dt(r["created_at"]) or datetime.now())
                session.add(entry)
                session.commit()
                dom["schedule_entries"]["migrated"] += 1
            except IntegrityError:
                session.rollback()
                dom["schedule_entries"]["skipped"] += 1
            except Exception as exc:
                session.rollback()
                _fail(dom["schedule_entries"], r["id"], exc)

        # 4. habits + habit_logs
        rows = _rows(cur, "habits", ["id", "name", "notes", "period", "target_count",
                                     "color", "sort_order", "created_at", "deleted_at"],
                     dom["habits"])
        for r in rows or []:
            try:
                habit = Habit(name=r["name"] or "未命名", notes=r["notes"] or "",
                              period=r["period"] or "daily", target_count=int(r["target_count"] or 1),
                              color=r["color"] or "#22c55e", sort_order=float(r["sort_order"] or 0.0),
                              created_at=_parse_dt(r["created_at"]) or datetime.now(),
                              deleted_at=_parse_dt(r["deleted_at"]))
                commit_row(habit, "habits", r["id"], "habits")
            except Exception as exc:
                session.rollback()
                _fail(dom["habits"], r["id"], exc)
        rows = _rows(cur, "habit_logs", ["id", "habit_id", "date", "count"], dom["habit_logs"])
        for r in rows or []:
            try:
                if r["habit_id"] not in id_map["habits"]:
                    dom["habit_logs"]["skipped"] += 1
                    continue
                log = HabitLog(habit_id=id_map["habits"][r["habit_id"]],
                               date=_parse_date(r["date"]), count=int(r["count"] or 0))
                session.add(log)
                session.commit()
                dom["habit_logs"]["migrated"] += 1
            except IntegrityError:
                session.rollback()
                dom["habit_logs"]["skipped"] += 1
            except Exception as exc:
                session.rollback()
                _fail(dom["habit_logs"], r["id"], exc)

        # 5. goals + key_results
        rows = _rows(cur, "goals", ["id", "title", "notes", "status", "start_date",
                                    "end_date", "sort_order", "created_at", "deleted_at"],
                     dom["goals"])
        for r in rows or []:
            try:
                goal = Goal(title=r["title"] or "未命名", notes=r["notes"] or "",
                            status=r["status"] or "active", start_date=_parse_date(r["start_date"]),
                            end_date=_parse_date(r["end_date"]),
                            sort_order=float(r["sort_order"] or 0.0),
                            created_at=_parse_dt(r["created_at"]) or datetime.now(),
                            deleted_at=_parse_dt(r["deleted_at"]))
                commit_row(goal, "goals", r["id"], "goals")
            except Exception as exc:
                session.rollback()
                _fail(dom["goals"], r["id"], exc)
        rows = _rows(cur, "key_results", ["id", "goal_id", "title", "kind", "target_value",
                                          "current_value", "unit", "link", "created_at"],
                     dom["key_results"])
        for r in rows or []:
            try:
                if r["goal_id"] not in id_map["goals"]:
                    dom["key_results"]["skipped"] += 1
                    continue
                kr = KeyResult(goal_id=id_map["goals"][r["goal_id"]], title=r["title"] or "",
                               kind=r["kind"] or "manual", target_value=float(r["target_value"] or 0),
                               current_value=float(r["current_value"] or 0), unit=r["unit"] or "",
                               link=r["link"] or "",
                               created_at=_parse_dt(r["created_at"]) or datetime.now())
                session.add(kr)
                session.commit()
                dom["key_results"]["migrated"] += 1
            except Exception as exc:
                session.rollback()
                _fail(dom["key_results"], r["id"], exc)

        # 6. journal_entries（date 唯一，重复跳过）
        rows = _rows(cur, "journal_entries", ["id", "date", "content", "mood",
                                              "created_at", "updated_at"], dom["journal"])
        for r in rows or []:
            try:
                entry = JournalEntry(date=_parse_date(r["date"]), content=r["content"] or "",
                                     mood=r["mood"], created_at=_parse_dt(r["created_at"]) or datetime.now(),
                                     updated_at=_parse_dt(r["updated_at"]) or datetime.now())
                session.add(entry)
                session.commit()
                dom["journal"]["migrated"] += 1
            except IntegrityError:
                session.rollback()
                dom["journal"]["skipped"] += 1
            except Exception as exc:
                session.rollback()
                _fail(dom["journal"], r["id"], exc)

        # 7. time_logs（任务已删/未迁 → task_title 冗余仍在，task_id 置空）
        rows = _rows(cur, "time_logs", ["id", "task_id", "task_title", "kind", "started_at",
                                        "ended_at", "minutes", "created_at"], dom["time_logs"])
        for r in rows or []:
            try:
                log = TimeLog(task_id=id_map["tasks"].get(r["task_id"]),
                              task_title=r["task_title"] or "", kind=r["kind"] or "focus",
                              started_at=_parse_dt(r["started_at"]) or datetime.now(),
                              ended_at=_parse_dt(r["ended_at"]),
                              minutes=int(r["minutes"] or 0),
                              created_at=_parse_dt(r["created_at"]) or datetime.now())
                session.add(log)
                session.commit()
                dom["time_logs"]["migrated"] += 1
            except Exception as exc:
                session.rollback()
                _fail(dom["time_logs"], r["id"], exc)

        # 8. files（链接直迁；文件给 attachments 则拷贝+解析回填，否则仅落记录）
        rows = _rows(cur, "files", ["id", "original_name", "storage_path", "size", "mime_type",
                                    "notes", "source_url", "resource_type", "uploaded_at",
                                    "deleted_at"], dom["files"])
        for r in rows or []:
            try:
                rtype = r["resource_type"] or "file"
                spath = (r["storage_path"] or "").strip()
                uploaded = _parse_dt(r["uploaded_at"]) or datetime.now()
                if rtype == "link" or spath.startswith(("http://", "https://")):
                    row = LibraryFile(original_name=r["original_name"] or spath,
                                      storage_path=spath, size=0, mime_type="text/uri-list",
                                      notes=r["notes"] or "", source_url=r["source_url"] or spath,
                                      resource_type="link", uploaded_at=uploaded,
                                      deleted_at=_parse_dt(r["deleted_at"]))
                    session.add(row)
                    session.commit()
                    dom["files"]["migrated"] += 1
                    id_map["files"][r["id"]] = row.id
                    continue
                src = _resolve_source(attachments, spath) if attachments else None
                if src is not None:
                    row = save_local_file(session, storage_root=storage_root,
                                          source=src, notes=r["notes"] or "")
                    row.mime_type = r["mime_type"] or row.mime_type
                    row.source_url = r["source_url"]
                    row.resource_type = "file"
                    row.uploaded_at = uploaded
                    row.deleted_at = _parse_dt(r["deleted_at"])
                    session.commit()
                    dom["files"]["copied"] += 1
                    try:
                        ensure_parsed(session, row, storage_root=storage_root)
                        dom["files"]["parsed"] += 1
                    except Exception:
                        dom["files"]["note"] = dom["files"]["note"] or "部分附件解析失败（记录已迁，可稍后重试）"
                else:  # 无 attachments 目录或源文件缺失：只落记录，路径原样保留
                    row = LibraryFile(original_name=r["original_name"] or "未命名",
                                      storage_path=spath.replace("\\", "/") or f"lost/{r['id']}",
                                      size=int(r["size"] or 0),
                                      mime_type=r["mime_type"] or "application/octet-stream",
                                      notes=r["notes"] or "", source_url=r["source_url"],
                                      resource_type="file", uploaded_at=uploaded,
                                      deleted_at=_parse_dt(r["deleted_at"]))
                    session.add(row)
                    session.commit()
                    dom["files"]["note"] = dom["files"]["note"] or "未提供 --attachments：文件记录已迁，实体待重挂"
                dom["files"]["migrated"] += 1
                id_map["files"][r["id"]] = row.id
            except IntegrityError:
                session.rollback()
                dom["files"]["skipped"] += 1
            except Exception as exc:
                session.rollback()
                _fail(dom["files"], r["id"], exc)

        # 9. task_file 关联（按新旧 id 映射重建）
        rows = _rows(cur, "task_file", ["task_id", "file_id"], dom["task_file_links"])
        for r in rows or []:
            try:
                if (r["task_id"] not in id_map["tasks"]) or (r["file_id"] not in id_map["files"]):
                    dom["task_file_links"]["skipped"] += 1
                    continue
                new_tid, new_fid = id_map["tasks"][r["task_id"]], id_map["files"][r["file_id"]]
                session.execute(task_file.insert().values(task_id=new_tid, file_id=new_fid))
                session.commit()
                dom["task_file_links"]["migrated"] += 1
            except IntegrityError:
                session.rollback()
                dom["task_file_links"]["skipped"] += 1
            except Exception as exc:
                session.rollback()
                _fail(dom["task_file_links"], f"{r['task_id']}:{r['file_id']}", exc)

        # 10. app_settings（白名单）
        rows = _rows(cur, "app_settings", ["key", "value"], dom["settings"])
        for r in rows or []:
            try:
                if r["key"] not in _SETTINGS_KEYS and not r["key"].startswith(_SETTINGS_PREFIXES):
                    dom["settings"]["skipped"] += 1
                    continue
                row = session.get(AppSetting, r["key"])
                if row is None:
                    row = AppSetting(key=r["key"], value=r["value"] or "")
                    session.add(row)
                else:
                    row.value = r["value"] or ""
                session.commit()
                dom["settings"]["migrated"] += 1
            except Exception as exc:
                session.rollback()
                _fail(dom["settings"], r["key"], exc)

        session.close()
        engine.dispose()
    finally:
        con.close()

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="知时 v1 → v2 一次性数据迁移（源库只读）")
    parser.add_argument("--from", dest="old_db", required=True, type=Path, help="旧版 app.db 路径")
    parser.add_argument("--data-dir", dest="data_dir", type=Path, default=Path("data/v2"),
                        help="新版数据目录（v2 根，含 backend.db 与 attachments/）")
    parser.add_argument("--attachments", type=Path, default=None,
                        help="旧版 data 目录（含 files/），提供时拷贝附件并触发解析")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", help="只报告不写入")
    args = parser.parse_args(argv)

    try:
        report = migrate(args.old_db, args.data_dir, dry_run=args.dry_run,
                         attachments=args.attachments)
    except FileNotFoundError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    print(json.dumps({k: v for k, v in report.items() if k != "id_map"},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
