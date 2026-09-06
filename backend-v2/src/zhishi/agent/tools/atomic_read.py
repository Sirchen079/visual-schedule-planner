# src/zhishi/agent/tools/atomic_read.py
"""L1 只读工具：包装 M1 领域服务，返回模型可读的紧凑文本。
签名约定：第一参数 db: Session（runtime 负责注入），其余参数即工具 schema。"""
from __future__ import annotations
import json
from datetime import date
from sqlalchemy.orm import Session
from zhishi.agent.tools.registry import ToolSpec, register


def _json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def get_current_time(db: Session) -> str:
    """获取当前日期时间（含星期与时区说明）。回答"今天/明天/本周"等相对日期问题、
    或在创建任何带日期的对象前，必须先调用本工具校准时间基准。"""
    from zhishi.infra.local_clock import snapshot
    return _json(snapshot())


def resolve_local_date(db: Session, expression: str, reference_date: str | None = None) -> str:
    """将今天/明天/后天/下周一/月底/N天后等换算为明确日期，含星期和采用的规则。
    reference_date为该条用户消息时间块的YYYY-MM-DD；省略则使用调用时本机日期。
    审批恢复或跨午夜后继续处理原消息时必须传原消息日期，不能自动顺延已确认的安排。
    不支持的模糊表达会返回错误，应向用户核对，不猜日期。"""
    from zhishi.infra.local_clock import resolve_date
    return _json(resolve_date(expression, reference_date))


def list_tasks(db: Session, query: str | None = None, status: str | None = None,
               priority: str | None = None, tag: str | None = None) -> str:
    """查询任务列表（不写任何数据）。query 按标题模糊匹配；status: todo/doing/done；
    priority: high/medium/low；tag 按标签名过滤。修改/删除任务前必须先用本工具定位目标 task_id。"""
    from zhishi.domain.tasks import service as ts
    tasks = ts.list_tasks(db, status=status, priority=priority, q=query, tag=tag)
    return _json([{"id": t.id, "title": t.title, "status": t.status, "priority": t.priority,
                   "due_date": t.due_date.isoformat() if t.due_date else None,
                   "tags": [x.name for x in t.tags]} for t in tasks[:50]])


def get_task(db: Session, task_id: int) -> str:
    """查看单个任务详情（含子任务与附件）。"""
    from zhishi.domain.tasks import service as ts
    t = ts.get_task(db, task_id)
    return _json({"id": t.id, "title": t.title, "notes": t.notes, "status": t.status,
                  "due_date": t.due_date.isoformat() if t.due_date else None,
                  "subtasks": [{"id": s.id, "title": s.title, "done": s.done} for s in t.subtasks],
                  "tags": [x.name for x in t.tags]})


def list_day_schedule(db: Session, day: str) -> str:
    """查看某天的统一日程视图（任务排期 + 独立日程块合并，按时间排序）。day 格式 YYYY-MM-DD。
    排程/冲突判断前先看当天已有安排。"""
    from zhishi.domain.schedule import service as ss
    return _json(ss.unified_day(db, date.fromisoformat(day)))


def list_month_schedule(db: Session, year: int, month: int) -> str:
    """查看某月每日任务数概览（压力分布）。"""
    from zhishi.domain.schedule import service as ss
    return _json(ss.month_schedule(db, year, month))


def get_range_load(db: Session, start: str, days: int) -> str:
    """查看自 start 起 days 天的排程负载：每日任务明细与预估总分钟数。做排程建议前使用。"""
    from zhishi.domain.schedule import service as ss
    return _json(ss.range_load(db, date.fromisoformat(start), days))


def find_free_slots(db: Session, day: str, min_minutes: int = 30) -> str:
    """查找某天工作时段内的空闲时段（≥min_minutes 连续段）。安排新事项前先查空闲。"""
    from zhishi.domain.schedule import conflicts as cf
    from zhishi.domain import settingsvc
    working = settingsvc.working_hours(db)
    return _json(cf.find_free_slots(db, date.fromisoformat(day), working=working,
                                    min_minutes=min_minutes))


def check_conflicts(db: Session, start: str, end: str) -> str:
    """检测日期范围内带时刻项目的重叠冲突。"""
    from zhishi.domain.schedule import conflicts as cf
    return _json(cf.check_conflicts(db, date.fromisoformat(start), date.fromisoformat(end)))


def list_habits(db: Session) -> str:
    """列出习惯及今日打卡状态与连续纪录。"""
    from zhishi.domain.habits import service as hs
    out = []
    for h in hs.list_habits(db):
        st = hs.habit_status(db, h.id)
        out.append({"id": h.id, "name": h.name, "period": h.period,
                    "target_count": h.target_count, **st})
    return _json(out)


def list_goals(db: Session) -> str:
    """列出目标（OKR）及各关键结果进度。"""
    from zhishi.domain.goals import service as gs
    out = []
    for g in gs.list_goals(db):
        out.append({"id": g.id, "title": g.title,
                    "status": g.status, "key_results": gs.goal_progress(db, g.id)})
    return _json(out)


def list_journal_entries(db: Session, limit: int = 10) -> str:
    """列出最近的日记（含心情）。"""
    from zhishi.domain.journal import service as js
    return _json([{"date": e.date.isoformat(), "mood": e.mood,
                   "content": e.content[:200]} for e in js.list_entries(db, limit=limit)])


def get_time_stats(db: Session, days: int = 7) -> str:
    """最近 N 天专注时间统计：每日分钟数、任务排行。复盘或排程建议前使用。"""
    from zhishi.domain.focus import service as fs
    return _json(fs.time_stats(db, days=days))


def list_files(db: Session, query: str | None = None) -> str:
    """列出资料库文件/链接资源。"""
    from zhishi.domain.library import service as ls
    return _json([{"id": f.id, "name": f.original_name, "type": f.resource_type,
                   "notes": f.notes[:100]} for f in ls.list_files(db, q=query)])


def list_notifications(db: Session, limit: int = 20) -> str:
    """列出最近通知（提醒到点记录）。"""
    from zhishi.domain import notifications as ns
    return _json([{"id": n.id, "title": n.title, "remind_at": n.remind_at.isoformat(),
                   "read": n.read_at is not None} for n in ns.list_notifications(db, limit)])


def get_event(db: Session, event_id: int) -> str:
    """读取独立日程的完整时间、重复规则和提醒设置。修改日程或提醒前，先用本工具核对；
    event_id 来自 list_day_schedule。remind_offsets 是提前分钟，空数组表示关闭提醒。"""
    from zhishi.domain.schedule import service as ss
    event = ss.get_event(db, event_id)
    return _json({"event_id": event.id, "title": event.title, "date": event.date.isoformat(),
                  "start_time": event.start_time, "end_time": event.end_time,
                  "location": event.location, "notes": event.notes, "recur_rrule": event.recur_rrule,
                  "repeat_note": event.repeat_note, "remind_offsets": ss.event_reminder_offsets(event),
                  "reminder_time": event.reminder_time})


_READ_SPECS = [
    ToolSpec("get_event", get_event.__doc__ or "", "readonly", None, get_event),
    ToolSpec("resolve_local_date", resolve_local_date.__doc__ or "", "readonly", None, resolve_local_date),
    ToolSpec("get_current_time", get_current_time.__doc__ or "", "readonly", None, get_current_time),
    ToolSpec("list_tasks", list_tasks.__doc__ or "", "readonly", None, list_tasks),
    ToolSpec("get_task", get_task.__doc__ or "", "readonly", None, get_task),
    ToolSpec("list_day_schedule", list_day_schedule.__doc__ or "", "readonly", None, list_day_schedule),
    ToolSpec("list_month_schedule", list_month_schedule.__doc__ or "", "readonly", None, list_month_schedule),
    ToolSpec("get_range_load", get_range_load.__doc__ or "", "readonly", None, get_range_load),
    ToolSpec("find_free_slots", find_free_slots.__doc__ or "", "readonly", None, find_free_slots),
    ToolSpec("check_conflicts", check_conflicts.__doc__ or "", "readonly", None, check_conflicts),
    ToolSpec("list_habits", list_habits.__doc__ or "", "readonly", "feature_habits_enabled", list_habits),
    ToolSpec("list_goals", list_goals.__doc__ or "", "readonly", "feature_goals_enabled", list_goals),
    ToolSpec("list_journal_entries", list_journal_entries.__doc__ or "", "readonly",
             "feature_journal_enabled", list_journal_entries),
    ToolSpec("get_time_stats", get_time_stats.__doc__ or "", "readonly", "feature_focus_enabled", get_time_stats),
    ToolSpec("list_files", list_files.__doc__ or "", "readonly", "feature_library_enabled", list_files),
    ToolSpec("list_notifications", list_notifications.__doc__ or "", "readonly", None, list_notifications),
]


def _install() -> None:
    try:
        import zhishi.agent.tools.atomic_write  # noqa: F401 触发写类注册（任务 5 补全）
    except ImportError:
        pass
    import zhishi.agent.tools.macro_specs  # noqa: F401 触发 L2/L3 大颗粒工具注册
    for spec in _READ_SPECS:
        register(spec)


_install()
