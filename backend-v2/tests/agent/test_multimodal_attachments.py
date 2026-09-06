"""Offline routing contracts; no provider keys, network, or child processes."""
import asyncio
import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic_ai.messages import BinaryContent, ModelRequest, ToolReturnPart, UserPromptPart

from zhishi.agent import attachments as media
from zhishi.domain.models import LibraryFile, MCPServer
from zhishi.server.routes.vision import save_vision


def config(*modalities, provider='openai_compat'):
    return SimpleNamespace(provider_kind=provider, input_modalities_json=json.dumps(modalities))


@pytest.fixture
def file(db, tmp_path):
    root = tmp_path / 'attachments'
    root.mkdir()
    (root / 'pic.png').write_bytes(b'\x89PNG-test')
    row = LibraryFile(original_name='pic.png', storage_path='attachments/pic.png',
                      mime_type='image/png', size=9)
    db.add(row)
    db.commit()
    return row


@pytest.fixture
def server(db):
    row = MCPServer(name='vision', transport='http', url='http://unused.invalid/mcp',
                    enabled=True, auto_approve_readonly=True)
    db.add(row)
    db.commit()
    save_vision(media.VisionConfig(enabled=True, server_id=row.id, tool_name='describe'), db)
    return row


@pytest.fixture
def mcp(monkeypatch):
    state = SimpleNamespace(builds=0, calls=[], readonly=True, tools=True,
                            result=SimpleNamespace(content=[
                                SimpleNamespace(type='text', text='课表：星期一数学')]),
                            error=None, on_list=None)

    class Toolset:
        client = None

        def __init__(self):
            self.client = self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def list_tools(self):
            if state.on_list:
                state.on_list()
            return [SimpleNamespace(name='describe', description='', input_schema={},
                                    annotations=SimpleNamespace(read_only_hint=state.readonly))
                    ] if state.tools else []

        async def call_tool(self, **kwargs):
            state.calls.append(kwargs)
            if state.error:
                raise state.error
            return state.result

    def build(*args, **kwargs):
        state.builds += 1
        return Toolset()

    monkeypatch.setattr(media.mcp_client, 'build_toolset', build)
    return state


async def run(db, file, tmp_path, cfg=None, prompt='读这张图'):
    return await media.process_media(db, cfg, file, tmp_path / 'attachments', prompt)


@pytest.mark.parametrize('provider', ['openai_compat', 'openai_responses', 'anthropic'])
async def test_declared_image_is_native_without_mcp(db, file, tmp_path, mcp, server, provider):
    result = await run(db, file, tmp_path, config('text', 'image', provider=provider))
    assert result.route == 'native' and result.status == 'supplied'
    assert result.binary.data == b'\x89PNG-test'
    assert result.binary.media_type == 'image/png'
    assert mcp.builds == 0


@pytest.mark.parametrize('cfg', [None, config('text'),
                                SimpleNamespace(input_modalities_json='broken'),
                                SimpleNamespace(input_modalities_json='"image"')])
async def test_default_never_native(db, file, tmp_path, mcp, cfg):
    result = await run(db, file, tmp_path, cfg)
    assert result.binary is None and result.status == 'unavailable'
    assert '内容未读取' in result.text
    assert mcp.builds == 0


async def test_text_model_uses_designated_tool_and_prompt_once(db, file, tmp_path, server, mcp):
    prompt = 'literal {{image_path}} "quote"'
    result = await run(db, file, tmp_path, config('text'), prompt)
    assert result.route == 'vision_mcp' and result.status == 'read' and result.binary is None
    assert '星期一数学' in result.text
    assert len(mcp.calls) == 1
    call = mcp.calls[0]
    assert call['name'] == 'describe'
    assert call['arguments']['prompt'] == prompt  # no recursive template evaluation
    assert call['arguments']['image'].startswith('data:image/png;base64,')
    assert str(tmp_path) not in json.dumps(call)


@pytest.mark.parametrize(('attribute', 'value'), [
    ('enabled', False), ('auto_approve_readonly', False), ('url', 'http://changed.invalid/mcp'),
    ('created_at', datetime(2000, 1, 1, tzinfo=UTC)),
    ('headers_json', '{"Authorization":"changed"}')])
async def test_server_change_invalidates_consent(db, file, tmp_path, server, mcp,
                                                attribute, value):
    setattr(server, attribute, value)
    db.commit()
    result = await run(db, file, tmp_path, config('text'))
    assert result.status != 'read' and mcp.builds == 0


@pytest.mark.parametrize('readonly', [False, None])
async def test_not_readonly_never_executes_even_with_grant(db, file, tmp_path, server, mcp,
                                                        readonly):
    from zhishi.domain.models import AIToolGrant
    db.add(AIToolGrant(tool_name=f'mcp__{server.id}__describe', arg_pattern=''))
    db.commit()
    mcp.readonly = readonly
    result = await run(db, file, tmp_path, config('text'))
    assert result.status == 'approval_required' and not mcp.calls


async def test_revoked_while_listing_does_not_call(db, file, tmp_path, server, mcp):
    def revoke():
        server.auto_approve_readonly = False
        db.commit()
    mcp.on_list = revoke
    result = await run(db, file, tmp_path, config('text'))
    assert result.status != 'read' and not mcp.calls


async def test_tool_missing(db, file, tmp_path, server, mcp):
    mcp.tools = False
    result = await run(db, file, tmp_path, config('text'))
    assert '不存在' in result.error and not mcp.calls


@pytest.mark.parametrize('result', [
    SimpleNamespace(content=[SimpleNamespace(type='image', data='binary')]),
    SimpleNamespace(content=[SimpleNamespace(type='text', text='   ')]),
    SimpleNamespace(content=[SimpleNamespace(type='resource_link', uri='https://unused.invalid')]),
    SimpleNamespace(content=[SimpleNamespace(type='text', text='secret-error')], is_error=True),
    {'answer': 'unverified structured output'},
])
async def test_tool_requires_actual_successful_text(db, file, tmp_path, server, mcp, result):
    mcp.result = result
    output = await run(db, file, tmp_path, config('text'))
    assert output.status == 'error' and '内容未读取' in output.text
    assert 'secret-error' not in output.text
    assert len(mcp.calls) == 1


async def test_upstream_exception_never_leaks_payload(db, file, tmp_path, server, mcp):
    mcp.error = RuntimeError('Authorization sk-real-secret data:image/png;base64,PRIVATE /secret/path')
    result = await run(db, file, tmp_path, config('text'))
    assert result.status == 'error'
    assert all(secret not in result.text for secret in ('sk-real-secret', 'PRIVATE', '/secret/path'))


async def test_cancellation_propagates(db, file, tmp_path, server, mcp):
    mcp.error = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await run(db, file, tmp_path, config('text'))


async def test_nested_template_and_trusted_local_path(db, file, tmp_path, server, mcp):
    server.transport, server.command, server.trusted = 'stdio', 'unused-command', True
    db.commit()
    save_vision(media.VisionConfig(enabled=True, server_id=server.id, tool_name='describe',
                                  arguments={'input': [{'path': '{{image_path}}'}],
                                             'label': '{{filename}}:{{mime_type}}'}), db)
    result = await run(db, file, tmp_path, config('text'))
    assert result.status == 'read'
    assert mcp.calls[0]['arguments']['input'][0]['path'] == str(
        (tmp_path / 'attachments' / 'pic.png').resolve())
    assert mcp.calls[0]['arguments']['label'] == 'pic.png:image/png'
    server.trusted = False
    db.commit()
    result = await run(db, file, tmp_path, config('text'))
    assert result.status == 'approval_required' and mcp.builds == 1


@pytest.mark.parametrize(('name', 'mime', 'kind'), [
    ('image.jpg', 'application/octet-stream', 'image'),
    ('recording.WAV', 'application/octet-stream', 'audio'),
    ('clip.MP4', 'application/octet-stream', 'video'),
    ('file', 'audio/mp3', 'audio'), ('paper.pdf', 'application/pdf', None)])
def test_detect_before_parser(name, mime, kind):
    assert media.detect_media(SimpleNamespace(original_name=name, mime_type=mime)) == kind


@pytest.mark.parametrize(('mime', 'provider', 'declared', 'native'), [
    ('audio/wav', 'openai_compat', True, True),
    ('audio/mp3', 'openai_compat', True, True),
    ('audio/x-wav', 'openai_compat', True, True),
    ('audio/ogg', 'openai_compat', True, False),
    ('audio/wav', 'openai_compat', False, False),
    ('audio/wav', 'openai_responses', True, False),
    ('audio/mpeg', 'anthropic', True, False),
    ('video/mp4', 'openai_compat', True, False),
    ('video/mp4', 'openai_responses', True, False),
    ('video/mp4', 'anthropic', True, False),
])
async def test_transport_gates_without_mcp(db, file, tmp_path, mcp, server,
                                         mime, provider, declared, native):
    file.mime_type = mime
    cfg = config('text', *([mime.split('/')[0]] if declared else []), provider=provider)
    result = await run(db, file, tmp_path, cfg)
    assert (result.binary is not None) == native
    assert result.status == ('supplied' if native else 'unsupported')
    assert mcp.builds == 0


@pytest.mark.parametrize('problem', ['escape', 'absolute_escape', 'missing', 'empty',
                                    'large', 'directory', 'deleted', 'external_resource'])
async def test_read_failures_no_binary_or_call(db, file, tmp_path, mcp, problem):
    path = tmp_path / 'attachments' / 'pic.png'
    if problem in ('escape', 'absolute_escape'):
        outside = tmp_path / 'private.png'
        outside.write_bytes(b'secret')
        file.storage_path = '../private.png' if problem == 'escape' else str(outside)
    elif problem == 'missing':
        path.unlink()
    elif problem == 'empty':
        path.write_bytes(b'')
    elif problem == 'large':
        with path.open('wb') as stream:
            stream.truncate(media.MAX_MEDIA_BYTES + 1)
        file.size = 1  # recorded upload size is not trusted
    elif problem == 'directory':
        file.storage_path = 'attachments'
    elif problem == 'deleted':
        file.deleted_at = datetime.now(UTC)
    else:
        file.resource_type = 'link'
    result = await run(db, file, tmp_path, config('text', 'image'))
    assert result.binary is None and '内容未读取' in result.text
    assert mcp.builds == 0


def test_exact_limit(tmp_path, monkeypatch):
    root = tmp_path / 'attachments'
    root.mkdir()
    monkeypatch.setattr(media, 'MAX_MEDIA_BYTES', 10)
    (root / 'pic.png').write_bytes(b'x' * 10)
    assert len(media._read_bounded(root, 'attachments/pic.png')[1]) == 10


def test_symlink_containment(tmp_path):
    root = tmp_path / 'attachments'
    root.mkdir()
    outside = tmp_path / 'private.png'
    outside.write_bytes(b'secret')
    try:
        (root / 'link.png').symlink_to(outside)
    except OSError:
        pytest.skip('Windows symlink privilege unavailable')
    with pytest.raises(ValueError, match='目录'):
        media._read_bounded(root, 'attachments/link.png')


async def test_only_byte_io_runs_in_worker(db, file, tmp_path, monkeypatch):
    owner = threading.get_ident()
    original = media._read_bounded
    seen = []

    def bounded(root, path):
        assert isinstance(root, Path) and isinstance(path, str)
        seen.append(threading.get_ident())
        return original(root, path)

    monkeypatch.setattr(media, '_read_bounded', bounded)
    result = await run(db, file, tmp_path, config('image'))
    assert result.binary is not None and seen[0] != owner


async def test_history_text_only_removes_user_and_nested_tool_binary():
    image = BinaryContent(data=b'image', media_type='image/png')
    history = [ModelRequest(parts=[UserPromptPart(['question', image]),
                                   ToolReturnPart('describe', {'nested': [image, 'OCR text']},
                                                  tool_call_id='call-1')])]
    result = await media.sanitize_history_media(history, config('text'))
    assert '未读取' in result[0].parts[0].content[1]
    assert '未读取' in result[0].parts[1].content['nested'][0]
    assert result[0].parts[1].content['nested'][1] == 'OCR text'
    assert result[0].parts[1].tool_call_id == 'call-1'
    assert history[0].parts[0].content[1] is image
    assert history[0].parts[1].content['nested'][0] is image


@pytest.mark.parametrize('provider', ['openai_compat', 'openai_responses', 'anthropic'])
async def test_history_declared_supported_images_preserved(provider):
    image = BinaryContent(data=b'image', media_type='image/png')
    history = [ModelRequest(parts=[UserPromptPart(['OCR report', image]),
                                   ToolReturnPart('image_tool', image, tool_call_id='id')])]
    result = await media.sanitize_history_media(history, config('image', provider=provider))
    assert result[0].parts[0].content == ['OCR report', image]
    assert isinstance(result[0].parts[1].content,
                      str if provider == 'openai_compat' else BinaryContent)


async def test_history_audio_transport_gate_and_no_config():
    audio = BinaryContent(data=b'wav', media_type='audio/wav')
    history = [ModelRequest(parts=[UserPromptPart([audio])])]
    for cfg in (None, config('audio', provider='openai_responses'),
                config('audio', provider='anthropic')):
        result = await media.sanitize_history_media(history, cfg)
        assert isinstance(result[0].parts[0].content[0], str)
    result = await media.sanitize_history_media(history, config('audio'))
    assert result[0].parts[0].content[0] is audio


async def test_hook_sanitizes_new_tool_results_each_request_and_snapshots_config():
    from pydantic_ai import Agent
    from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
    from pydantic_ai.models.function import FunctionModel

    cfg = config('text')
    hooks = media.media_capability_hooks(cfg)
    cfg.input_modalities_json = '["text", "image"]'  # closure must keep its snapshot
    calls = []

    def model_function(messages, info):
        calls.append(messages)
        if len(calls) == 1:
            assert isinstance(messages[-1].parts[-1].content[1], str)
            return ModelResponse(parts=[ToolCallPart('fetch_image', {}, tool_call_id='image-1')])
        returns = [part for message in messages if isinstance(message, ModelRequest)
                   for part in message.parts if isinstance(part, ToolReturnPart)]
        assert len(returns) == 1
        assert isinstance(returns[0].content, str) and '未读取' in returns[0].content
        assert returns[0].tool_call_id == 'image-1'
        return ModelResponse(parts=[TextPart('请提供附件文字。')])

    agent = Agent(FunctionModel(model_function), capabilities=[hooks])

    @agent.tool_plain
    def fetch_image() -> BinaryContent:
        return BinaryContent(data=b'tool-image', media_type='image/png')

    result = await agent.run(['describe', BinaryContent(data=b'user-image', media_type='image/png')])
    assert result.output == '请提供附件文字。' and len(calls) == 2


async def test_hook_preserves_declared_current_native_image():
    from pydantic_ai import Agent
    from pydantic_ai.messages import ModelResponse, TextPart
    from pydantic_ai.models.function import FunctionModel

    image = BinaryContent(data=b'user-image', media_type='image/png')

    def model_function(messages, info):
        assert messages[-1].parts[-1].content == ['describe', image]
        return ModelResponse(parts=[TextPart('received')])

    agent = Agent(FunctionModel(model_function),
                  capabilities=[media.media_capability_hooks(config('text', 'image'))])
    assert (await agent.run(['describe', image])).output == 'received'


async def test_installed_mcp_stack_returns_raw_text_in_process(db, file, tmp_path,
                                                             server, monkeypatch):
    from mcp.server.mcpserver import MCPServer as InProcessServer
    from mcp.types import ToolAnnotations

    endpoint = InProcessServer(name='offline-vision')
    calls = []

    def describe(image: str, prompt: str) -> str:
        calls.append((image, prompt))
        return '文字：星期一数学'

    endpoint.add_tool(describe, name='describe', description='read supplied image',
                      annotations=ToolAnnotations(read_only_hint=True))
    monkeypatch.setattr(media.mcp_client, 'build_client', lambda row: (endpoint, {}))
    result = await run(db, file, tmp_path, config('text'))
    assert result.status == 'read', result.error
    assert '星期一数学' in result.text and len(calls) == 1
