"""Keep changing context at the message tail, outside the stable instruction prefix."""
from dataclasses import replace
import json
import hashlib
from urllib.parse import urlsplit

from pydantic_ai.capabilities import Hooks
from zhishi.infra.local_clock import live_instructions
from zhishi.agent.context_parts import adapt_cache_points, append_context


def live_clock_hooks(config=None, conversation_id=None):
    def prepare(ctx, request):
        # Copy: never rewrite stored user timestamps or previous message parts.
        # Tool results remain together and in order in their original request.
        explicit = (getattr(request.model, 'settings', None) or {}).get('anthropic_cache_messages')
        ttl = explicit if isinstance(explicit, str) else '5m'
        messages = adapt_cache_points(request.messages, ttl if explicit else None)
        from zhishi.agent.cache_gateway import CACHE_BOUNDARY, CachedGatewayChatModel
        if isinstance(request.model, CachedGatewayChatModel):
            messages = append_context(messages, 'cache-boundary', CACHE_BOUNDARY)
        messages = append_context(messages, 'clock', live_instructions(), cache_before=bool(explicit),
                                  cache_ttl=ttl)
        settings = request.model_settings
        if explicit:
            settings = {**(settings or {}), 'anthropic_cache_messages': False}
        protocol = getattr(config, 'provider_kind', None)
        if protocol in ('openai_compat', 'openai_responses') and getattr(config, 'prompt_cache_mode', None) != 'disabled':
            preference = getattr(config, 'prompt_cache_key', None)
            host = urlsplit(str(getattr(getattr(request.model, 'client', None), 'base_url', ''))).hostname
            if preference is True or preference is None and host == 'api.openai.com':
                cid = conversation_id if conversation_id is not None else getattr(getattr(ctx, 'deps', None), 'conversation_id', None)
                if cid is not None:
                    key = hashlib.sha256(f'zhishi:{getattr(config, "id", "")}:conversation:{cid}'.encode()).hexdigest()
                    settings = {**(settings or {}), 'openai_prompt_cache_key': key}
        parameters = request.model_request_parameters
        # MCP discovery order and JSON object insertion order must not invalidate a
        # previously identical tool set. Arrays and the actual schema stay intact.
        definitions = [replace(tool, parameters_json_schema=json.loads(json.dumps(
            tool.parameters_json_schema, sort_keys=True, ensure_ascii=False)))
            for tool in sorted(parameters.function_tools, key=lambda tool: tool.name)]
        return replace(request, messages=messages, model_settings=settings,
                       model_request_parameters=replace(parameters, function_tools=definitions))

    return Hooks(before_model_request=prepare)
