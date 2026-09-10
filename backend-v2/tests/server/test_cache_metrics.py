import json

from zhishi.agent.cache_metrics import cache_stats
from zhishi.domain.models import AIConversation, AIRun, AIUsageLog


def test_weighted_rate_and_historical_coverage(db):
    conversation = AIConversation(title='test')
    db.add(conversation)
    db.flush()
    for index, (tokens, read) in enumerate([(100, 0), (9900, 9900), (2000, None)]):
        usage = {'input_tokens': tokens}
        if read is not None:
            usage.update(cache_read_tokens=read, cache_write_tokens=0)
        db.add(AIRun(run_id=str(index), conversation_id=conversation.id,
                     usage_json=json.dumps(usage), status='completed'))
        db.add(AIUsageLog(run_id=str(index), provider='test', model='test',
                          prompt_tokens=tokens, total_tokens=tokens))
    db.commit()
    stats = cache_stats(db)
    assert stats.totals.cache_hit_rate == .99  # not a mean of 0% and 100%
    assert stats.totals.measured_records == 2
    assert stats.totals.usage_records == 3
    assert stats.totals.measurement_coverage == 10000 / 12000
    assert stats.by_model[0].cache_hit_rate == .99


def test_cache_endpoint_empty_and_validation(tmp_path):
    from fastapi.testclient import TestClient

    from zhishi.server.app import create_app
    with TestClient(create_app(data_dir=tmp_path)) as client:
        response = client.get('/ai/cache/stats')
        assert response.status_code == 200
        assert response.json()['totals']['cache_hit_rate'] is None
        assert client.get('/ai/cache/stats?days=0').status_code == 422
