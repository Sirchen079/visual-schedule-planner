"""Token-weighted cache metrics. Historical missing counters remain unknown."""
import json
from datetime import datetime, timedelta

from pydantic import BaseModel
from sqlalchemy import select

from zhishi.domain.models import AIRun, AIUsageLog


class CacheTotals(BaseModel):
    usage_records: int = 0
    measured_records: int = 0
    input_tokens: int = 0
    measured_input_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cache_hit_rate: float | None = None
    measurement_coverage: float | None = None


class ModelCacheTotals(CacheTotals):
    provider: str
    model: str


class CacheStats(BaseModel):
    days: int
    metric: str = 'sum(cache_read_tokens) / sum(measured_input_tokens)'
    scope: str = ('logged AI usage; chat includes child agents; unmeasured records excluded; '
                  'SDK-normalized counters, absent provider cache counters count as zero')
    totals: CacheTotals
    by_model: list[ModelCacheTotals]


def cache_stats(db, *, days: int = 7) -> CacheStats:
    rows = db.execute(select(AIUsageLog.provider, AIUsageLog.model,
        AIUsageLog.prompt_tokens, AIRun.usage_json)
        .outerjoin(AIRun, AIRun.run_id == AIUsageLog.run_id)
        # Database timestamps follow the application's naive local-time contract.
        .where(AIUsageLog.created_at >= datetime.now() - timedelta(days=days)))  # noqa: DTZ005
    totals = CacheTotals()
    groups = {}
    for provider, model, tokens, raw in rows:
        group = groups.setdefault((provider, model),
            ModelCacheTotals(provider=provider, model=model))
        try:
            usage = json.loads(raw or '{}')
        except (TypeError, ValueError):
            usage = {}
        read = usage.get('cache_read_tokens') if isinstance(usage, dict) else None
        write = usage.get('cache_write_tokens') if isinstance(usage, dict) else None
        measured = (type(read) is int and type(write) is int
                    and 0 <= read <= tokens and 0 <= write <= tokens
                    and read + write <= tokens)
        for bucket in (totals, group):
            bucket.usage_records += 1
            bucket.input_tokens += tokens
            if measured:
                bucket.measured_records += 1
                bucket.measured_input_tokens += tokens
                bucket.cache_read_tokens += read
                bucket.cache_write_tokens += write
    for bucket in (totals, *groups.values()):
        if bucket.measured_input_tokens:
            bucket.cache_hit_rate = bucket.cache_read_tokens / bucket.measured_input_tokens
        if bucket.input_tokens:
            bucket.measurement_coverage = bucket.measured_input_tokens / bucket.input_tokens
    return CacheStats(days=days, totals=totals,
        by_model=[groups[key] for key in sorted(groups)])
