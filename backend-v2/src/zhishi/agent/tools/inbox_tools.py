import json

from sqlalchemy.orm import Session

from zhishi.agent.tools.registry import ToolSpec, register
from zhishi.domain.inbox import service
from zhishi.domain.inbox.schemas import Candidate, CaptureBatch, Revision


def propose_inbox_items(db: Session, ctx, items: list[Candidate]) -> str:
    """从材料整理待办/日程/收支候选到收件箱（不实际执行）。每项保留 source_excerpt，
    附件填 source_file_id；item_key 使用稳定原文位置如 p1-row2 或 receipt-total，重传/重试不要换键。
    相同文件字节会跨文件名去重；附件上下文已含处理记录，仅缺少记录或分页未全时调用 list_inbox_items。
    最少字段：task 的 data={title}；event 的 data={title,date}；
    event 可附 remind_offsets（提前分钟），全天提醒另填 reminder_time（HH:MM），不要另建任务。
    ledger 的 data={day,direction:expense或income,amount:十进制金额字符串}。
    公共结构为 {source_file_id,item_key,source_excerpt,proposal:{kind,data},uncertainty}。
    金额/日期等关键事实缺失时先澄清，不能为了通过参数校验编造；uncertainty 记录待澄清约束。
    返回已应用/已忽略表示该材料条目以前已处理，不要再用其他写工具创建副本。"""
    result = service.capture(db, CaptureBatch(capture_key=ctx.deps.capture_key, items=items))
    return json.dumps({"ok": True, "items": [r.model_dump(mode="json") for r in result],
        "next_step": "候选已保存。向用户列出候选与疑问，并提示打开收件箱核对；此时还没有创建实际任务、日程或账目。"
                     "applied/rejected 表示此前已处理，不能另建副本。用户要求修改时先 get_inbox_item 取最新版本。"},
                     ensure_ascii=False)


def list_inbox_items(db: Session, status: str | None = None, source_file_id: int | None = None,
                     limit: int = 50, offset: int = 0) -> str:
    """查看收件箱与处理结果。可按来源附件查找，字节相同的重复上传也可找到已有条目。
    status 可为 pending/applied/rejected，空表示全部；输出原文、疑问、目标和版本。"""
    return service.list_items(db, status, source_file_id, limit, offset).model_dump_json()


def get_inbox_item(db: Session, item_id: int) -> str:
    """读取收件箱完整候选、来源和最新版本；修改/应用/忽略之前使用。"""
    return service.to_read(db, service.get_item(db, item_id)).model_dump_json()


def revise_inbox_item(db: Session, item_id: int, revision: Revision) -> str:
    """基于已澄清事实修正候选；先读取当前版本。解决疑问后 uncertainty 清空；已忽略可修订回待确认。"""
    return service.revise(db, item_id, revision).model_dump_json()


def apply_inbox_item(db: Session, item_id: int, version: int) -> str:
    """用户确认后，把一条无未解疑问的候选落实为真实任务/日程/账目。
    确认与目标创建同事务，重试不重复写；不替用户决定未澄清的金额、时间等。"""
    return service.apply_item(db, item_id, version).model_dump_json()


def reject_inbox_item(db: Session, item_id: int, version: int) -> str:
    """忽略一条材料候选，不创建目标；保留来源，可通过修订重新放回待确认。"""
    return service.reject(db, item_id, version).model_dump_json()


for fn, safety in [(propose_inbox_items, "safe"), (list_inbox_items, "readonly"),
                   (get_inbox_item, "readonly"), (revise_inbox_item, "confirm"),
                   (apply_inbox_item, "confirm"), (reject_inbox_item, "confirm")]:
    register(ToolSpec(fn.__name__, fn.__doc__ or "", safety, None, fn))
