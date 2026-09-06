# tests/agent/test_providers.py
from zhishi.agent.providers import build_model, resolve_api_key


def test_openai_compat_model_uses_base_url(db):
    from zhishi.domain.models import AIConfig
    cfg = AIConfig(name="智谱", provider_kind="openai_compat", model="glm-5.3-flash",
                   base_url="https://open.bigmodel.cn/api/paas/v4", api_key_ref="test-key-1")
    db.add(cfg); db.commit()
    model = build_model(cfg, api_key="sk-x")
    assert type(model).__name__ == "OpenAIChatModel"


def test_anthropic_model(db):
    from zhishi.domain.models import AIConfig
    cfg = AIConfig(name="claude", provider_kind="anthropic", model="claude-sonnet-4-6",
                   base_url=None, api_key_ref="test-key-2")
    db.add(cfg); db.commit()
    model = build_model(cfg, api_key="sk-ant")
    assert "Anthropic" in type(model).__name__


def test_resolve_api_key_prefers_keyring(monkeypatch):
    from zhishi.infra import secrets
    monkeypatch.setattr(secrets, "load_api_key", lambda name: "from-keyring" if name == "r1" else None)
    assert resolve_api_key("r1") == "from-keyring"
    assert resolve_api_key("missing") is None


def test_responses_protocol_uses_local_history_without_server_storage(db):
    from zhishi.domain.models import AIConfig
    cfg = AIConfig(name='Responses',provider_kind='openai_responses',model='example',
                   base_url='https://example.org/v1',api_key_ref='test-responses')
    model = build_model(cfg,api_key='test-placeholder')
    assert type(model).__name__ == 'OpenAIResponsesModel'
    assert model.settings['openai_store'] is False
    assert str(model.client.base_url) == 'https://example.org/v1/'
