from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Currency = Literal["CNY", "USD", "EUR", "GBP", "HKD", "JPY"]
Direction = Literal["income", "expense"]
DIGITS = {"CNY": 2, "USD": 2, "EUR": 2, "GBP": 2, "HKD": 2, "JPY": 0}


class EntryData(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    day: date
    direction: Direction
    amount: Decimal = Field(gt=0, le=Decimal("999999999.99"), max_digits=11,
                            decimal_places=2, allow_inf_nan=False)
    currency: Currency = "CNY"
    category: str = Field(default="未分类", min_length=1, max_length=50)
    account: str = Field(default="默认账户", min_length=1, max_length=80)
    payee: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=10000)
    source_file_id: int | None = Field(default=None, gt=0)
    source_excerpt: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def exact_amount(self):
        parts = self.amount.as_tuple()
        fractional = -int(parts.exponent)
        for digit in reversed(parts.digits):
            if digit != 0:
                break
            fractional -= 1
        if fractional > DIGITS[self.currency]:
            raise ValueError(f"{self.currency} 金额最多 {DIGITS[self.currency]} 位小数，不能四舍五入记账")
        return self

    @property
    def amount_minor(self) -> int:
        return int(self.amount * (10 ** DIGITS[self.currency]))


class EntryCreate(EntryData):
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=160)


class EntryReplace(EntryData):
    version: int = Field(ge=1)


class VersionInput(BaseModel):
    version: int = Field(ge=1)


class EntryRead(BaseModel):
    id: int
    day: date
    direction: Direction
    amount: str
    amount_minor: int
    currency: Currency
    category: str
    account: str
    payee: str
    notes: str
    source_file_id: int | None
    source_excerpt: str
    version: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class EntryPage(BaseModel):
    items: list[EntryRead]
    total: int
    limit: int
    offset: int


class CategoryTotal(BaseModel):
    category: str
    direction: Direction
    amount: str
    count: int


class CurrencyTotal(BaseModel):
    currency: Currency
    income: str
    expense: str
    net: str
    count: int
    categories: list[CategoryTotal]


class LedgerSummary(BaseModel):
    start: date
    end: date
    currencies: list[CurrencyTotal]
