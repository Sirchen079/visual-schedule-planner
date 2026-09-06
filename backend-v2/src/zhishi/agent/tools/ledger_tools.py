from datetime import date

from sqlalchemy.orm import Session

from zhishi.agent.tools.registry import ToolSpec, register
from zhishi.domain.ledger import service
from zhishi.domain.ledger.schemas import Currency, Direction, EntryCreate, EntryReplace


def record_transaction(db: Session, entry: EntryCreate) -> str:
    """记录个人收入或支出。amount 使用十进制字符串（如 '28.50'），day 为明确日期。
    支持 CNY/USD/EUR/GBP/HKD/JPY。来源收据填 source_file_id 与 source_excerpt；
    同一凭据重试复用 idempotency_key（如 receipt:文件id:条目序号），不要将合计和明细重复记账。
    只记录用户明确的实际收支；预算/报价/未支付订单不当作实际支出。"""
    return service.to_read(service.create_entry(db, entry)).model_dump_json()


def list_transactions(db: Session, start: date | None = None, end: date | None = None,
                      currency: Currency | None = None, account: str | None = None,
                      direction: Direction | None = None, query: str = "", deleted: bool = False,
                      limit: int = 50, offset: int = 0) -> str:
    """查账，按日期、币种、账户、收支方向、分类/商户/备注关键词过滤；分页最多 200。
    deleted=true 查账本回收站；修改或删除前读取 id 与 version。"""
    return service.list_entries(db, start=start, end=end, currency=currency, account=account,
        direction=direction, query=query, deleted=deleted, limit=limit, offset=offset).model_dump_json()


def get_transaction(db: Session, entry_id: int) -> str:
    """读取完整账目、凭据来源和当前 version；包括回收站状态，修改/恢复前使用。"""
    return service.to_read(service.get_entry(db, entry_id)).model_dump_json()


def summarize_transactions(db: Session, start: date, end: date,
                           currency: Currency | None = None, account: str | None = None) -> str:
    """汇总指定日期范围的实际收入、支出、净收支和分类明细；币种分别合计，不推测汇率。"""
    return service.summary(db, start, end, currency=currency, account=account).model_dump_json()


def update_transaction(db: Session, entry_id: int, entry: EntryReplace) -> str:
    """修正已有账目，先 get_transaction 后传回完整内容与 version，避免覆盖他人新修改。"""
    return service.to_read(service.replace_entry(db, entry_id, entry, entry.version)).model_dump_json()


def delete_transaction(db: Session, entry_id: int, version: int) -> str:
    """将账目移入账本回收站（可恢复），先读取当前 id/version；汇总随之排除此笔。"""
    return service.to_read(service.delete_entry(db, entry_id, version)).model_dump_json()


def restore_transaction(db: Session, entry_id: int, version: int) -> str:
    """恢复账本回收站中的一笔账目，先读取当前 id/version；恢复后重新纳入汇总。"""
    return service.to_read(service.restore_entry(db, entry_id, version)).model_dump_json()


for fn, safety in [(record_transaction, "safe"), (list_transactions, "readonly"),
                   (get_transaction, "readonly"), (summarize_transactions, "readonly"),
                   (update_transaction, "confirm"), (delete_transaction, "confirm"),
                   (restore_transaction, "confirm")]:
    register(ToolSpec(fn.__name__, fn.__doc__ or "", safety, None, fn))
