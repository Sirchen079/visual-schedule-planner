# src/zhishi/agent/tools/atomic_write.py
"""L1 写类工具（safe + confirm）：与只读同构（第一参数 db，返回 JSON 文本）。
confirm 组函数体同样完整实现——审批通过后由 runtime 复用同一函数执行
（审批不是授权边界，工具内部照常校验），安全分级只登记在 ToolSpec；
不可豁免高危由 permissions.IRREVOCABLE_TOOLS 表达（单一数据源）。"""
from __future__ import annotations
import json
from datetime import date
from sqlalchemy.orm import Session
from zhishi.agent.tools.registry import ToolSpec, register


def _json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def create_task(db: Session, title: str, notes: str = "", due_date: str | None = None,
                due_time: str | None = None, priority: str = "medium",
                remind_offsets: list[int] | None = None, recur_rule: str = "none",
                recur_interval: int = 1, recur_rrule: str | None = None,
                estimated_minutes: int | None = None, tag_names: list[str] | None = None) -> str:
    """创建任务（低风险直写）。日期用 YYYY-MM-DD（可带时间）；提醒用 remind_offsets 提前分钟数组（如 [0,30,1440]）；
    重复规则 recur_rule: none/daily/weekdays/weekly/monthly，单双周/多选星期用 recur_rrule；
    指定几点提醒时，同时填 due_date、due_time（HH:MM）和 remind_offsets=[0]；未设置提醒数组不会提醒。
    超过 120 分钟的任务先拆子任务再排程。创建前先用 get_current_time 校准当前日期。"""
    from datetime import datetime
    from zhishi.domain.tasks import service as ts
    from zhishi.domain.tasks.schemas import TaskCreate
    payload = TaskCreate(
        title=title, notes=notes,
        due_date=datetime.fromisoformat(due_date) if due_date else None,
        due_time=due_time, priority=priority,
        remind_offsets=remind_offsets or [], recur_rule=recur_rule,
        recur_interval=recur_interval, recur_rrule=recur_rrule,
        estimated_minutes=estimated_minutes, tag_names=tag_names or [])
    task = ts.create_task(db, payload)
    return _json({"id": task.id, "title": task.title, "status": task.status})


def create_subtasks(db: Session, task_id: int, items: list[dict]) -> str:
    """为任务批量创建子任务（低风险直写）。items 每项 {title, estimated_minutes?}，按 title 去重。
    拆分大任务时用本工具创建真实子任务，不要只写进 notes。"""
    from zhishi.domain import subtasks as sb
    created, seen = [], set()
    for item in items:
        title = (item.get("title") or "").strip()
        if not title or title in seen:
            continue
        seen.add(title)
        sub = sb.create_subtask(db, task_id, title=title,
                                estimated_minutes=item.get("estimated_minutes"))
        created.append({"id": sub.id, "title": sub.title})
    return _json({"task_id": task_id, "created": created})


def assign_task_to_day(db: Session, task_id: int, day: str,
                       start_time: str | None = None, end_time: str | None = None,
                       note: str = "") -> str:
    """把任务排到某天（低风险直写，同日重复排 = 更新时间）。day 格式 YYYY-MM-DD；
    排程前先用 get_range_load 看负载、find_free_slots 找空闲、check_conflicts 查冲突。"""
    from zhishi.domain.schedule import service as ss
    entry = ss.assign_task_to_day(db, task_id, date.fromisoformat(day),
                                  start_time=start_time, end_time=end_time,
                                  source="ai", note=note)
    return _json({"entry_id": entry.id, "task_id": task_id, "date": day,
                  "start_time": entry.start_time, "end_time": entry.end_time})


def create_event(db: Session, title: str, day: str, start_time: str | None = None,
                 end_time: str | None = None, location: str = "", category: str = "general",
                 recur_rrule: str | None = None, notes: str = "",
                 remind_offsets: list[int] | None = None, reminder_time: str | None = None) -> str:
    """创建独立日程块（低风险直写）。课表/会议等固定日程用本工具，不要建成任务；
    重复日程用 recur_rrule（如 FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,WE）。day 格式 YYYY-MM-DD。
    日程提醒直接用 remind_offsets（提前分钟，如 [0,30]，最多8个，0至10080），不要另建提醒任务。
    无 start_time 的全天日程还须指定 reminder_time（HH:MM）；每天/周/月/年的每次日程都会按规则提醒。"""
    from zhishi.domain.schedule import service as ss
    event = ss.create_event(db, title=title, date=date.fromisoformat(day),
                            start_time=start_time, end_time=end_time, location=location,
                            category=category, recur_rrule=recur_rrule, notes=notes,
                            remind_offsets=remind_offsets or [], reminder_time=reminder_time)
    return _json({"event_id": event.id, "title": event.title, "date": day,
                  "remind_offsets": ss.event_reminder_offsets(event), "reminder_time": event.reminder_time})


def check_in_habit(db: Session, habit_id: int, day: str | None = None) -> str:
    """习惯打卡（低风险直写，当天幂等累加）。day 缺省为今天。"""
    from zhishi.domain.habits import service as hs
    log = hs.check_in(db, habit_id, date.fromisoformat(day) if day else None)
    return _json({"habit_id": habit_id, "date": log.date.isoformat(), "count": log.count})


def write_journal(db: Session, content: str, mood: str | None = None,
                  day: str | None = None) -> str:
    """写日记（低风险直写）。一天一篇：同一天再次写入为覆盖更新。day 缺省为今天。"""
    from zhishi.domain.journal import service as js
    entry = js.upsert(db, date.fromisoformat(day) if day else date.today(),
                      content=content, mood=mood)
    return _json({"date": entry.date.isoformat(), "mood": entry.mood})


def update_kr_progress(db: Session, kr_id: int, current_value: float) -> str:
    """手动更新关键结果进度（低风险直写）。仅 kind=manual 的 KR 有效。"""
    from zhishi.domain.goals import service as gs
    kr = gs.update_kr_progress(db, kr_id, current_value=current_value)
    return _json({"kr_id": kr.id, "current_value": kr.current_value})


def start_timer(db: Session, task_id: int | None = None, task_title: str = "",
                kind: str = "focus") -> str:
    """开始专注计时（低风险直写；全局至多一条运行中，新计时自动停旧的）。kind: focus/break。"""
    from zhishi.domain.focus import service as fs
    from zhishi.domain.focus.schemas import TimerStart
    log = fs.start_timer(db, TimerStart(task_id=task_id, task_title=task_title, kind=kind))
    return _json({"log_id": log.id, "started_at": log.started_at, "kind": log.kind})


def stop_timer(db: Session, log_id: int | None = None) -> str:
    """停止计时（低风险直写）。log_id 缺省停止当前运行中的计时。"""
    from zhishi.domain.focus import service as fs
    log = fs.stop_timer(db, log_id)
    if log is None:
        return _json({"ok": False, "note": "没有运行中的计时"})
    return _json({"log_id": log.id, "minutes": log.minutes})


def update_work_plan(db: Session, steps: list[dict]) -> str:
    """更新工作计划展示（纯元数据，低风险直写）。steps 每项 {title, status?}（status 缺省"待办"）。
    用于向用户展示当前执行计划，不落库、不影响任何业务数据。"""
    out = []
    for s in steps:
        if not (s.get("title") or "").strip():
            raise ValueError("工作计划的每个步骤必须有 title")
        out.append({"title": s["title"], "status": s.get("status") or "待办"})
    return _json({"steps": out})


def update_task(db: Session, task_id: int, title: str | None = None, notes: str | None = None,
                due_date: str | None = None, due_time: str | None = None,
                priority: str | None = None, status: str | None = None,
                remind_offsets: list[int] | None = None, recur_rule: str | None = None,
                recur_interval: int | None = None, recur_rrule: str | None = None,
                estimated_minutes: int | None = None, tag_names: list[str] | None = None,
                clear_due_date: bool = False, clear_due_time: bool = False) -> str:
    """修改任务（需确认）。修改前必须先用 list_tasks/get_task 定位目标 task_id；
    只传需要修改的字段，未传字段保持不变。取消提醒用 remind_offsets=[]；
    清空截止日期/时间用 clear_due_date/clear_due_time=true，不要传空字符串或 null。"""
    from datetime import datetime
    from zhishi.domain.tasks import service as ts
    fields: dict = {"title": title, "notes": notes,
                    "due_date": datetime.fromisoformat(due_date) if due_date else None,
                    "due_time": due_time, "priority": priority, "status": status,
                    "remind_offsets": remind_offsets, "recur_rule": recur_rule,
                    "recur_interval": recur_interval, "recur_rrule": recur_rrule,
                    "estimated_minutes": estimated_minutes, "tag_names": tag_names}
    fields = {k: v for k, v in fields.items() if v is not None}
    if clear_due_date:
        if due_date is not None:
            raise ValueError("清空截止日期时不能同时指定 due_date")
        fields["due_date"] = None
    if clear_due_time:
        if due_time is not None:
            raise ValueError("清空截止时间时不能同时指定 due_time")
        fields["due_time"] = None
    task = ts.update_task(db, task_id, **fields)
    return _json({"id": task.id, "title": task.title, "status": task.status,
                  "due_date": task.due_date, "due_time": task.due_time,
                  "remind_offsets": task.remind_offset_list})


def delete_task(db: Session, task_id: int) -> str:
    """删除任务（移入回收站，需确认）。删除前必须先用 list_tasks/get_task 确认目标。"""
    from zhishi.domain.tasks import service as ts
    ts.soft_delete_task(db, task_id)
    return _json({"ok": True, "task_id": task_id, "note": "已移入回收站"})


def update_schedule_entry(db: Session, entry_id: int, day: str | None = None,
                          start_time: str | None = None, end_time: str | None = None,
                          note: str | None = None) -> str:
    """修改任务排期（需确认）。先用 list_day_schedule 定位 entry_id。"""
    from zhishi.domain.schedule import service as ss
    from zhishi.domain.schedule.schemas import ScheduleEntryUpdate
    patch = ScheduleEntryUpdate(
        **{k: v for k, v in {"date": date.fromisoformat(day) if day else None,
                             "start_time": start_time, "end_time": end_time,
                             "note": note}.items() if v is not None})
    entry = ss.update_entry(db, entry_id, patch)
    return _json({"entry_id": entry.id, "date": entry.date.isoformat(),
                  "start_time": entry.start_time, "end_time": entry.end_time})


def delete_schedule_entry(db: Session, entry_id: int) -> str:
    """删除任务排期（需确认，不影响任务本身）。先用 list_day_schedule 定位 entry_id。"""
    from zhishi.domain.schedule import service as ss
    ss.delete_entry(db, entry_id)
    return _json({"ok": True, "entry_id": entry_id})


def update_event(db: Session, event_id: int, title: str | None = None, day: str | None = None,
                 start_time: str | None = None, end_time: str | None = None,
                 location: str | None = None, category: str | None = None,
                 recur_rrule: str | None = None, notes: str | None = None,
                 remind_offsets: list[int] | None = None, reminder_time: str | None = None) -> str:
    """修改独立日程（需确认）。先用 list_day_schedule 定位 event_id。
    remind_offsets=[] 关闭后续提醒；其他数组设置提前分钟；不传则保留。全天提醒须给 reminder_time。
    重复日程的修改作用于整个系列，先明确用户要改整个系列。"""
    from zhishi.domain.schedule import service as ss
    from zhishi.domain.schedule.schemas import EventUpdate
    fields = {"title": title, "date": date.fromisoformat(day) if day else None,
              "start_time": start_time, "end_time": end_time, "location": location,
              "category": category, "recur_rrule": recur_rrule, "notes": notes,
              "remind_offsets": remind_offsets, "reminder_time": reminder_time}
    event = ss.update_event(db, event_id, EventUpdate(
        **{k: v for k, v in fields.items() if v is not None}))
    return _json({"event_id": event.id, "title": event.title,
                  "remind_offsets": ss.event_reminder_offsets(event), "reminder_time": event.reminder_time})


def delete_event(db: Session, event_id: int) -> str:
    """删除独立日程（需确认，不可恢复）。先用 list_day_schedule 定位 event_id。"""
    from zhishi.domain.schedule import service as ss
    ss.delete_event(db, event_id)
    return _json({"ok": True, "event_id": event_id})


def update_habit(db: Session, habit_id: int, name: str | None = None,
                 notes: str | None = None, target_count: int | None = None,
                 period: str | None = None) -> str:
    """修改习惯（需确认）。period: daily/weekly。"""
    from zhishi.domain.models import Habit
    habit = db.get(Habit, habit_id)
    if habit is None or habit.deleted_at is not None:
        raise LookupError(f"habit {habit_id} 不存在")
    for key, value in {"name": name, "notes": notes,
                       "target_count": target_count, "period": period}.items():
        if value is not None:
            setattr(habit, key, value)
    db.commit()
    return _json({"habit_id": habit_id, "name": habit.name})


def delete_habit(db: Session, habit_id: int) -> str:
    """删除习惯（软删除，需确认）。"""
    from zhishi.domain.habits import service as hs
    hs.delete_habit(db, habit_id)
    return _json({"ok": True, "habit_id": habit_id})


def update_goal(db: Session, goal_id: int, title: str | None = None,
                notes: str | None = None, status: str | None = None) -> str:
    """修改目标（需确认）。status: active/paused/done/archived。"""
    from zhishi.domain.goals import service as gs
    fields = {k: v for k, v in {"title": title, "notes": notes, "status": status}.items()
              if v is not None}
    goal = gs.update_goal(db, goal_id, **fields)
    return _json({"goal_id": goal.id, "title": goal.title})


def delete_goal(db: Session, goal_id: int) -> str:
    """删除目标（软删除，需确认）。"""
    from zhishi.domain.goals import service as gs
    gs.delete_goal(db, goal_id)
    return _json({"ok": True, "goal_id": goal_id})


def update_subtask(db: Session, task_id: int, subtask_id: int, title: str | None = None,
                   done: bool | None = None, estimated_minutes: int | None = None) -> str:
    """修改子任务（需确认）。done 置 true/false 勾选完成；父任务进度自动重算。"""
    from zhishi.domain import subtasks as sb
    fields = {k: v for k, v in {"title": title, "done": done,
                                "estimated_minutes": estimated_minutes}.items()
              if v is not None}
    sub = sb.update_subtask(db, task_id, subtask_id, **fields)
    return _json({"subtask_id": sub.id, "title": sub.title, "done": sub.done})


def delete_subtask(db: Session, task_id: int, subtask_id: int) -> str:
    """删除子任务（需确认）。"""
    from zhishi.domain import subtasks as sb
    sb.delete_subtask(db, task_id, subtask_id)
    return _json({"ok": True, "subtask_id": subtask_id})


def empty_trash(db: Session) -> str:
    """清空回收站（不可恢复，需确认且不可设为始终允许）。"""
    from zhishi.domain.tasks import service as ts
    from zhishi.domain.library import service as ls
    purged = 0
    for task in ts.list_trash(db):
        ts.purge_task(db, task.id)
        purged += 1
    files = ls.list_trash(db)
    for f in files:
        ls.purge(db, f.id)  # 物理文件清理由 M3 解析管道统一处理
        purged += 1
    return _json({"ok": True, "purged": purged})


def bulk_delete_tasks(db: Session, task_ids: list[int]) -> str:
    """批量软删除任务（不可豁免高危，需确认）。先用只读工具确认全部 task_id。"""
    from zhishi.domain.tasks import service as ts
    deleted, missing = [], []
    for tid in task_ids:
        try:
            ts.soft_delete_task(db, tid)
            deleted.append(tid)
        except LookupError:
            missing.append(tid)
    return _json({"deleted": deleted, "missing": missing})


def bulk_delete_files(db: Session, file_ids: list[int]) -> str:
    """批量软删除资料文件（不可豁免高危，需确认）。先用 list_files 确认全部 file_id。"""
    from zhishi.domain.library import service as ls
    deleted, missing = [], []
    for fid in file_ids:
        try:
            ls.soft_delete(db, fid)
            deleted.append(fid)
        except LookupError:
            missing.append(fid)
    return _json({"deleted": deleted, "missing": missing})


def import_web_resources(db: Session, resources: list[dict]) -> str:
    """批量导入网页/链接资源（不可豁免高危，需确认）。每项 {title, url, notes?}，
    url 必须以 http(s):// 开头；M2 仅登记链接，内容抓取解析在后续版本增强。"""
    from zhishi.domain.library import service as ls
    created = []
    for item in resources:
        title = (item.get("title") or "").strip()
        url = (item.get("url") or "").strip()
        if not title or not url.startswith(("http://", "https://")):
            raise ValueError(f"资源项缺少 title 或 url 非法：{item}")
        row = ls.save_link(db, title=title, url=url, notes=item.get("notes") or "",
                           resource_type="link")
        created.append({"id": row.id, "title": row.title})
    return _json({"created": created})


_WRITE_SPECS = [
    ToolSpec("create_task", create_task.__doc__ or "", "safe", None, create_task),
    ToolSpec("create_subtasks", create_subtasks.__doc__ or "", "safe", None, create_subtasks),
    ToolSpec("assign_task_to_day", assign_task_to_day.__doc__ or "", "safe", None, assign_task_to_day),
    ToolSpec("create_event", create_event.__doc__ or "", "safe", None, create_event),
    ToolSpec("check_in_habit", check_in_habit.__doc__ or "", "safe", "feature_habits_enabled", check_in_habit),
    ToolSpec("write_journal", write_journal.__doc__ or "", "safe", "feature_journal_enabled", write_journal),
    ToolSpec("update_kr_progress", update_kr_progress.__doc__ or "", "safe", "feature_goals_enabled", update_kr_progress),
    ToolSpec("start_timer", start_timer.__doc__ or "", "safe", "feature_focus_enabled", start_timer),
    ToolSpec("stop_timer", stop_timer.__doc__ or "", "safe", "feature_focus_enabled", stop_timer),
    ToolSpec("update_work_plan", update_work_plan.__doc__ or "", "safe", None, update_work_plan),
    ToolSpec("update_task", update_task.__doc__ or "", "confirm", None, update_task),
    ToolSpec("delete_task", delete_task.__doc__ or "", "confirm", None, delete_task),
    ToolSpec("update_schedule_entry", update_schedule_entry.__doc__ or "", "confirm", None, update_schedule_entry),
    ToolSpec("delete_schedule_entry", delete_schedule_entry.__doc__ or "", "confirm", None, delete_schedule_entry),
    ToolSpec("update_event", update_event.__doc__ or "", "confirm", None, update_event),
    ToolSpec("delete_event", delete_event.__doc__ or "", "confirm", None, delete_event),
    ToolSpec("update_habit", update_habit.__doc__ or "", "confirm", "feature_habits_enabled", update_habit),
    ToolSpec("delete_habit", delete_habit.__doc__ or "", "confirm", "feature_habits_enabled", delete_habit),
    ToolSpec("update_goal", update_goal.__doc__ or "", "confirm", "feature_goals_enabled", update_goal),
    ToolSpec("delete_goal", delete_goal.__doc__ or "", "confirm", "feature_goals_enabled", delete_goal),
    ToolSpec("update_subtask", update_subtask.__doc__ or "", "confirm", None, update_subtask),
    ToolSpec("delete_subtask", delete_subtask.__doc__ or "", "confirm", None, delete_subtask),
    ToolSpec("empty_trash", empty_trash.__doc__ or "", "confirm", None, empty_trash),
    ToolSpec("bulk_delete_tasks", bulk_delete_tasks.__doc__ or "", "confirm", None, bulk_delete_tasks),
    ToolSpec("bulk_delete_files", bulk_delete_files.__doc__ or "", "confirm", "feature_library_enabled", bulk_delete_files),
    ToolSpec("import_web_resources", import_web_resources.__doc__ or "", "confirm", "feature_library_enabled", import_web_resources),
]


def _install() -> None:
    for spec in _WRITE_SPECS:
        register(spec)


_install()
