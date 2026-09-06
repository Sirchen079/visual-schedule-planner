import httpx
from fastapi.testclient import TestClient

from zhishi.adapters import model_catalog
from zhishi.server.app import create_app


def test_model_list_does_not_create_config_or_store_key(tmp_path,monkeypatch,caplog):
    discover=model_catalog.discover_models
    def serve(request):
        assert request.headers['Authorization']=='Bearer temporary-test-key'
        return httpx.Response(200,json={'data':[{'id':'test-model'}]})
    monkeypatch.setattr(model_catalog,'discover_models',lambda body:discover(body,transport=httpx.MockTransport(serve)))
    from zhishi.infra import secrets
    def forbid(*args):
        raise AssertionError('model discovery must not save a key')
    monkeypatch.setattr(secrets,'store_api_key',forbid)
    with TestClient(create_app(data_dir=tmp_path)) as client:
        result=client.post('/ai/configs/models',json={'base_url':'https://models.example/v1','api_key':'temporary-test-key','provider_kind':'openai_responses'})
        assert result.status_code==200 and result.json()['models'][0]['id']=='test-model'
        assert client.get('/ai/configs').json()==[]
        assert client.get('/ai/conversations').json()==[]
        denied=client.post('/ai/configs/models',json={'base_url':'https://models.example/v1'},headers={'Origin':'https://other.example'})
        assert denied.status_code==403
    assert 'temporary-test-key' not in caplog.text
