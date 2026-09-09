"""Opt-in block cache hints for gateways translating Chat Completions to Anthropic.

Never enabled by guessing a model name. Standard OpenAI requests retain their wire shape.
"""
from pydantic_ai.models.openai import OpenAIChatModel

CACHE_BOUNDARY = '【本次上下文已就绪】'


class CachedGatewayChatModel(OpenAIChatModel):
    def __init__(self, *args, cache_ttl='5m', **kwargs):
        super().__init__(*args, **kwargs)
        self.cache_ttl = cache_ttl

    async def _map_messages(self, messages, model_request_parameters, *, model_settings=None):
        result = await super()._map_messages(messages, model_request_parameters, model_settings=model_settings)
        systems = [item for item in result if item['role'] in ('system', 'developer')]
        boundaries = [item for item in result if item['role'] == 'user' and (
            item.get('content') == CACHE_BOUNDARY or any(
                isinstance(block, dict) and block.get('text') == CACHE_BOUNDARY
                for block in item.get('content', []) if isinstance(item.get('content'), list)))]
        # One system checkpoint plus the newest two immutable message boundaries.
        # Keeping a prior boundary also works when a gateway searches few blocks back.
        selected = [*systems[-1:], *boundaries[-2:]]
        if not boundaries:
            selected += [item for item in result if item['role'] == 'user'][-1:]
        for item in selected:
            content = item.get('content')
            if isinstance(content, str) and content:
                content = [{'type': 'text', 'text': content}]
                item['content'] = content
            if isinstance(content, list) and content:
                content[-1]['cache_control'] = {'type': 'ephemeral', 'ttl': self.cache_ttl}
        return result
