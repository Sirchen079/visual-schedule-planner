import json

from sqlalchemy.orm import Session

from zhishi.agent.tools.registry import ToolSpec, register
from zhishi.domain.ledger import bills
from zhishi.domain.ledger.bill_schemas import BillCreate, BillPayment, BillSkip, BillUpdate
from zhishi.domain.ledger.service import LedgerConflict


def _change(db, fn, args, next_call):
    try:
        return fn(db, *args).model_dump_json()
    except LedgerConflict as exc:
        db.rollback()
        return json.dumps({'ok':False,'code':'bill_conflict','error':str(exc),
            'next_call':next_call, 'next_step':'读取最新账单及关联支出；已处理时停止，不换期次或直接记账绕过冲突。'},ensure_ascii=False)


def _next(occurrence_id):
    return {'tool':'get_bill_occurrence','args':{'occurrence_id':occurrence_id}}


def create_bill(db: Session, bill: BillCreate) -> str:
    """建立未支付账单及到期提醒，不计入支出。需明确 first_due、cycle(once/weekly/monthly/yearly)，
    amount可空表示待确认；request_key同一次创建重试复用。周期按首次日期计算，月末自动按当月末日。
    不推测订阅、支付状态或重复日期。返回pending.id供确认支付/跳过使用。"""
    return _change(db, bills.create, (bill,), {'tool':'list_bills','args':{}})


def list_bills(db: Session, limit: int = 10, offset: int = 0) -> str:
    """分页查询周期/一次性账单和最早未处理期次。暂停仍保留待支付记录；不能据此称已付款。"""
    return bills.list_bills(db, limit=limit, offset=offset).model_dump_json()


def get_bill(db: Session, bill_id: int) -> str:
    """读账单及pending当前期次id/version；支付、跳过、修改前使用。paid账目修改请用get_transaction。"""
    return bills.read(db, bill_id).model_dump_json()


def get_bill_history(db: Session, bill_id: int, before: int | None = None) -> str:
    """每次读5期账单历史、支付确认及关联实际账目，next_before非空时继续分页。
    关联账目deleted_at非空表示已在回收站，不要重新记账或假定仍计入支出。"""
    return bills.history(db, bill_id, before, limit=5).model_dump_json()


def get_bill_occurrence(db: Session, occurrence_id: int) -> str:
    """按准确期次id读取账单状态/version/已关联账目；支付冲突或补记历史期次前使用。"""
    return bills.read_occurrence(db, occurrence_id).model_dump_json()


def update_bill(db: Session, bill_id: int, bill: BillUpdate) -> str:
    """更新未处理期次和未来账单的预估金额/名称/账户/提醒；enabled=false暂停，历史支付不变。
    先get_bill获取version。变更首次到期或重复周期需暂停原账单后按明确新日期建新账单。"""
    return _change(db, bills.replace, (bill_id, bill), {'tool':'get_bill','args':{'bill_id':bill_id}})


def confirm_bill_payment(db: Session, occurrence_id: int, payment: BillPayment) -> str:
    """仅当用户明确已支付，确认指定期次并原子记账；不是实际银行付款。先get_bill/历史获取期次version。
    必填实际day/amount/account。若已记账，填existing_entry_id关联，金额/日期/账户/币种须一致。
    重试同一期同内容只返回原账目，勿额外record_transaction。跳过期次可在历史中补记支付。"""
    return _change(db, bills.pay, (occurrence_id, payment), _next(occurrence_id))


def skip_bill_occurrence(db: Session, occurrence_id: int, skip: BillSkip) -> str:
    """用户明确本期无需支付时跳过，必须填写原因和当前期次version，不产生支出。
    下一期待办自动出现；暂停后续提醒用update_bill(enabled=false)。"""
    return _change(db, bills.skip, (occurrence_id, skip), _next(occurrence_id))


for fn, safety in [(create_bill, 'safe'), (list_bills, 'readonly'), (get_bill, 'readonly'), (get_bill_occurrence, 'readonly'),
                   (get_bill_history, 'readonly'), (update_bill, 'confirm'),
                   (confirm_bill_payment, 'confirm'), (skip_bill_occurrence, 'confirm')]:
    register(ToolSpec(fn.__name__, fn.__doc__ or '', safety, None, fn))
