from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from zhishi.domain.ledger.schemas import Currency, EntryData, EntryRead


class BillDetails(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=200)
    amount: Decimal | None = Field(default=None, gt=0, le=Decimal('999999999.99'),
                                  max_digits=11, decimal_places=2, allow_inf_nan=False)
    currency: Currency = 'CNY'
    category: str = Field(default='居住', min_length=1, max_length=50)
    account: str = Field(default='默认账户', min_length=1, max_length=80)
    payee: str = Field(default='', max_length=200)
    notes: str = Field(default='', max_length=2000)
    remind_days: int = Field(default=3, ge=0, le=30)
    enabled: bool = True

    @model_validator(mode='after')
    def exact(self):
        if self.amount is not None:
            EntryData(day=date(2000, 1, 1), direction='expense', amount=self.amount,
                      currency=self.currency)
        return self


class BillCreate(BillDetails):
    first_due: date
    cycle: Literal['once', 'weekly', 'monthly', 'yearly'] = 'monthly'
    request_key: str = Field(min_length=1, max_length=160)

    @model_validator(mode='after')
    def supported_date(self):
        if not 1900 <= self.first_due.year <= 2099:
            raise ValueError('首次到期日期须在 1900 至 2099 年之间')
        return self


class BillUpdate(BillDetails):
    version: int = Field(ge=1)


class BillPayment(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    version: int = Field(ge=1)
    day: date
    amount: Decimal = Field(gt=0, le=Decimal('999999999.99'), max_digits=11,
                            decimal_places=2, allow_inf_nan=False)
    account: str = Field(min_length=1, max_length=80)
    existing_entry_id: int | None = Field(default=None, gt=0)
    source_file_id: int | None = Field(default=None, gt=0)
    source_excerpt: str = Field(default='', max_length=4000)


class BillSkip(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500)


class BillOccurrenceRead(BaseModel):
    id: int
    bill_id: int
    sequence: int
    due: date
    details: BillDetails
    status: Literal['pending', 'paid', 'skipped']
    version: int
    ledger_entry: EntryRead | None
    resolution: dict | None
    resolved_at: datetime | None


class BillRead(BaseModel):
    id: int
    first_due: date
    cycle: str
    version: int
    details: BillDetails
    pending: BillOccurrenceRead | None


class BillPage(BaseModel):
    items: list[BillRead]
    total: int
    offset: int
    limit: int


class BillHistory(BaseModel):
    items: list[BillOccurrenceRead]
    next_before: int | None
