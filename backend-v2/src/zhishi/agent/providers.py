# src/zhishi/agent/providers.py
"""AIConfig → PydanticAI 模型装配：
openai_compat：任意 OpenAI 兼容端点（智谱国内/DeepSeek/通义/自建网关）
openai_responses：OpenAI Responses 格式端点（显式选择，保留本地完整历史）
anthropic：Anthropic 原生协议。API key 从 keyring（DPAPI）取。"""
from __future__ import annotations

from typing import Literal

from zhishi.domain.models import AIConfig

ReasoningEffort = Literal['none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max']


def validate_reasoning_effort(provider_kind: str, effort: str | None) -> None:
    if effort is None:
        return
    if effort not in ('none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max'):
        raise ValueError('无效的思考程度，请在模型设置中重新选择')
    if provider_kind == 'anthropic' and effort == 'minimal':
        raise ValueError('Anthropic 不支持 minimal 思考档位，请选择低、中、高等档位或跟随服务商')


def resolve_api_key(api_key_ref: str | None) -> str | None:
    if not api_key_ref:
        return None
    from zhishi.infra import secrets
    return secrets.load_api_key(api_key_ref)


def build_model(config: AIConfig, api_key: str | None = None):
    settings = {}
    if getattr(config, 'max_output_tokens', None):
        settings['max_tokens'] = config.max_output_tokens
    effort = getattr(config, 'reasoning_effort', None)
    validate_reasoning_effort(config.provider_kind, effort)
    if effort is not None:
        if config.provider_kind == 'anthropic':
            settings['anthropic_thinking'] = {'type': 'disabled' if effort == 'none' else 'adaptive'}
            if effort != 'none':
                settings['anthropic_effort'] = effort
        else:
            settings['openai_reasoning_effort'] = effort
    key = api_key or resolve_api_key(config.api_key_ref)
    if not key:
        raise ValueError(f"配置「{config.name}」缺少 API key（keyring 引用 {config.api_key_ref}）")
    if config.provider_kind == "anthropic":
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider
        provider = AnthropicProvider(api_key=key, base_url=config.base_url)
        return AnthropicModel(config.model, provider=provider, settings=settings)
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider
    provider = OpenAIProvider(base_url=config.base_url, api_key=key)
    if config.provider_kind == 'openai_responses':
        from pydantic_ai.models.openai import OpenAIResponsesModel
        return OpenAIResponsesModel(config.model, provider=provider,
                                    settings={**settings, 'openai_store': False})
    if config.provider_kind != 'openai_compat':
        raise ValueError(f'不支持的模型接口格式：{config.provider_kind}')
    return OpenAIChatModel(config.model, provider=provider, settings=settings)


def oneshot_text(model, system: str, user: str) -> str:
    """单次模型调用（无工具循环），供报告/自动档等后台生成使用。
    内部用 run_sync（自建事件循环），须在无运行中事件循环的线程调用
    （同步路由天然在线程池；调度器经 asyncio.to_thread）。"""
    from pydantic_ai import Agent
    agent = Agent(model, instructions=system, output_type=str, retries=1)
    return agent.run_sync(user).output
