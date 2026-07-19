"""iCal（RFC 5545 子集）导入导出：任务 ↔ .ics 文件。

导出：全部未删除任务生成为 VEVENT（含优先级扩展属性）。
导入：解析 VEVENT 的 SUMMARY/DESCRIPTION/DTSTART/DTEND/DUE 创建任务。
只实现日历应用互通所需的最小子集：属性折行展开、转义字符、日期/日期时间两种格式。
"""
from __future__ import annotations

from datetime import datetime

from app.models import Task


def _escape(text: str) -> str:
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _unescape(text: str) -> str:
    return (
        (text or "")
        .replace("\\n", "\n")
        .replace("\\N", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
    )


def _fmt_dt(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%S")


def export_tasks(tasks: list[Task]) -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Zhishi//Tasks//CN"]
    now = datetime.now()
    for t in tasks:
        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:task-{t.id}@zhishi")
        lines.append(f"DTSTAMP:{_fmt_dt(now)}")
        lines.append(f"SUMMARY:{_escape(t.title)}")
        start = t.start_date or t.due_date or t.created_at
        if start:
            lines.append(f"DTSTART:{_fmt_dt(start)}")
        end = t.end_date or t.due_date
        if end:
            lines.append(f"DTEND:{_fmt_dt(end)}")
        if t.notes:
            lines.append(f"DESCRIPTION:{_escape(t.notes)}")
        if t.tags:
            lines.append("CATEGORIES:" + ",".join(_escape(tag.name) for tag in t.tags))
        lines.append(f"STATUS:{'CONFIRMED' if t.status == '完成' else 'TENTATIVE'}")
        lines.append(f"X-ZHISHI-PRIORITY:{t.priority}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def parse_ical(content: str) -> list[dict]:
    """解析 .ics 为任务字段列表（跳过无标题的 VEVENT）。"""
    # 折行展开：以空格/制表符开头的行是上一行的延续
    unfolded: list[str] = []
    for raw in content.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and unfolded:
            unfolded[-1] += raw[1:]
        else:
            unfolded.append(raw)
    events: list[dict] = []
    current: dict | None = None
    for line in unfolded:
        upper = line.strip().upper()
        if upper == "BEGIN:VEVENT":
            current = {}
        elif upper == "END:VEVENT" and current is not None:
            events.append(current)
            current = None
        elif current is not None and ":" in line:
            name, value = line.split(":", 1)
            name = name.split(";")[0].strip().upper()  # 去掉 DTSTART;VALUE=DATE 的参数
            current[name] = value
    tasks = []
    for ev in events:
        title = _unescape(ev.get("SUMMARY", "")).strip()
        if not title:
            continue
        tasks.append(
            {
                "title": title[:200],
                "notes": _unescape(ev.get("DESCRIPTION", "")),
                "start_date": _parse_dt(ev.get("DTSTART")),
                "end_date": _parse_dt(ev.get("DTEND")),
                "due_date": _parse_dt(ev.get("DUE")) or _parse_dt(ev.get("DTEND")),
            }
        )
    return tasks


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip().rstrip("Z").replace("-", "").replace(":", "")
    for fmt in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M", "%Y%m%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None
