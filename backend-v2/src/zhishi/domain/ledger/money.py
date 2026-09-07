from decimal import Decimal
from typing import Annotated

from pydantic import Field


def _portable_decimal_schema(schema: dict) -> None:
    """Use a portable decimal pattern; numeric limits remain enforced by Decimal validation."""
    for branch in schema.get('anyOf', [schema]):
        if branch.get('type') == 'string':
            branch['pattern'] = r'^[+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$'


MoneyAmount = Annotated[
    Decimal,
    Field(gt=0, le=Decimal('999999999.99'), max_digits=11, decimal_places=2,
          allow_inf_nan=False, json_schema_extra=_portable_decimal_schema),
]
