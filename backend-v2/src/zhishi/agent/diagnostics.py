"""Compare prepared model prefixes without retaining their content."""
import hashlib
import hmac
import json
import secrets
import time
from collections import OrderedDict
from dataclasses import asdict

from pydantic_core import to_jsonable_python

from zhishi.infra.diagnostics import error_details, record

_SECRET = secrets.token_bytes(32)
_previous = OrderedDict()


def fingerprint(value):
    raw = json.dumps(to_jsonable_python(value, bytes_mode='base64'), ensure_ascii=False,
                     sort_keys=True, separators=(',', ':'), default=str).encode()
    return hmac.new(_SECRET, raw, hashlib.sha256).hexdigest()[:24]


def request_diagnostic_hooks(config, conversation_id, scope):
    from pydantic_ai.capabilities import Hooks
    state = {}

    def capture(ctx, request):
        params = request.model_request_parameters
        tools = fingerprint([asdict(t) for t in params.function_tools])
        from pydantic_ai.models import Model
        instructions = fingerprint(Model._get_instruction_parts(request.messages, params))
        settings = fingerprint(request.model_settings)
        service = fingerprint(getattr(config, 'base_url', None))
        parts = [fingerprint({k: v for k, v in asdict(p).items()
                              if k not in ('timestamp', 'metadata')})
                 for m in request.messages for p in m.parts]
        key = (scope, conversation_id)
        previous = _previous.get(key) if conversation_id is not None else state.get('previous')
        shared = 0
        if previous:
            for a, b in zip(previous['parts'], parts):
                if a != b:
                    break
                shared += 1
        current = {'tools': tools, 'instructions': instructions, 'parts': parts, 'settings': settings, 'service': service}
        state.update(previous=current, started=time.monotonic(), request_id=secrets.token_hex(12))
        if conversation_id is not None:
            _previous[key] = current
            _previous.move_to_end(key)
            while len(_previous) > 128:
                _previous.popitem(last=False)
        protocol = getattr(config, 'provider_kind', None)
        record('ai_request', request_id=state['request_id'],
               run=fingerprint(getattr(ctx.deps, 'run_id', None)),
               conversation=fingerprint(key), model=fingerprint(getattr(config, 'model', None)),
               protocol=protocol if protocol in ('openai_compat', 'openai_responses', 'anthropic') else 'other',
               tool_count=len(params.function_tools), tools_fingerprint=tools,
               instructions_fingerprint=instructions, part_count=len(parts),
               settings_fingerprint=settings, service_fingerprint=service,
               settings_changed=previous.get('settings') != settings if previous else False,
               service_changed=previous.get('service') != service if previous else False,
               has_previous=previous is not None, shared_prefix_parts=shared,
               previous_part_count=len(previous['parts']) if previous else 0,
               tools_changed=previous['tools'] != tools if previous else False,
               instructions_changed=previous['instructions'] != instructions if previous else False,
               history_changed=shared < len(previous['parts']) if previous else False)
        return request

    async def before(ctx, request):
        try:
            return capture(ctx, request)
        except Exception as error:  # noqa: BLE001 - diagnostic failures must never abort model requests
            record('application', level='WARNING', module='agent.diagnostics', **error_details(error))
            return request

    async def after(ctx, *, request_context, response):
        usage = response.usage
        record('ai_response', request_id=state.get('request_id'), outcome='completed',
               duration_ms=int((time.monotonic() - state.get('started', time.monotonic())) * 1000),
               **{k: getattr(usage, k, None) for k in
                  ('input_tokens', 'output_tokens', 'cache_read_tokens', 'cache_write_tokens')})
        return response

    async def failed(ctx, *, request_context, error):
        record('ai_response', request_id=state.get('request_id'), outcome='failed',
               status_code=getattr(error, 'status_code', None), **error_details(error))
        raise error

    return Hooks(before_model_request=before, after_model_request=after, model_request_error=failed)
