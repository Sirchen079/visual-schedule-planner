import httpx
import pytest

from zhishi.adapters import web
from zhishi.adapters import web_services as ws


def client(body, content_type='text/html'):
    return httpx.Client(transport=httpx.MockTransport(lambda req:
        httpx.Response(200, content=body, headers={'content-type': content_type})))


def test_document_retains_tail_and_plaintext_angle_brackets():
    body = ('<script>hidden()</script><h1>Guide</h1>' + '<p>Concepts &amp; practice.</p>' * 3000 +
            '<h2>LAST SECTION with required exercise</h2>').encode()
    with client(body) as c:
        result = web.fetch_document('https://1.1.1.1/guide', c)
        assert len(result.text) > 30_000 and result.text.endswith('LAST SECTION with required exercise')
        assert 'hidden' not in result.text and not result.partial
        assert len(web.fetch('https://1.1.1.1/guide', c)) == 8000
    with client(b'Compare x < y and y > z.\nThen practice.', 'text/plain') as c:
        assert web.fetch_document('https://1.1.1.1/guide.txt', c).text.startswith('Compare x < y')


def test_document_byte_and_text_caps_mark_partial(monkeypatch):
    monkeypatch.setattr(web, 'MAX_BYTES', 50)
    with client(b'a' * 100, 'text/plain') as c:
        result = web.fetch_document('https://1.1.1.1/', c)
    assert result.text == 'a' * 50 and result.partial
    assert any('2MB' in w for w in result.warnings)
    monkeypatch.setattr(web, 'MAX_DOCUMENT_CHARS', 10)
    with client(b'b' * 40, 'text/plain') as c:
        result = web.fetch_document('https://1.1.1.1/', c)
    assert result.text == 'b' * 10 and result.partial
    assert any('10' in w for w in result.warnings)


def test_document_rejects_binary_and_private_redirect():
    with client(b'%PDF-1.7 fake binary', 'application/pdf') as c, pytest.raises(ValueError, match='上传'):
        web.fetch_document('https://1.1.1.1/paper', c)
    visited = []
    def redirect(req):
        visited.append(str(req.url))
        return httpx.Response(302, headers={'location':'http://127.0.0.1/private'})
    with httpx.Client(transport=httpx.MockTransport(redirect)) as c, pytest.raises(ValueError, match='非公网'):
        web.fetch_document('https://1.1.1.1/paper', c)
    assert len(visited) == 1


def test_tavily_document_retains_redacted_full_body_and_uncertain_coverage(db, monkeypatch):
    monkeypatch.setattr(ws, '_tavily_key', lambda db: 'tvly-test-secret')
    body = 'tvly-test-secret ' + '正文' * 40_000 + '最后一道练习'
    def handler(req):
        return httpx.Response(200, json={'results':[{'url':'https://1.1.1.1/guide', 'raw_content':body}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        result = ws.fetch_document(db, 'https://1.1.1.1/guide', provider='tavily', client=c)
    assert result.text.endswith('最后一道练习') and len(result.text) > 8000
    assert 'tvly-test-secret' not in result.text
    assert result.partial and any('tavily' in w for w in result.warnings)


def test_mcp_document_keeps_service_selection_and_caps(db, monkeypatch):
    config = ws.WebServicesConfig(fetch_provider='mcp', mcp_fetch={'server_id':1, 'tool_name':'read'})
    monkeypatch.setattr(ws, 'get_config', lambda db: config)
    monkeypatch.setattr(ws, '_mcp', lambda *a, **k: ('credential ' + 'x' * 9000, ['credential']))
    monkeypatch.setattr(web, 'fetch_document', lambda *a, **k: pytest.fail('unexpected builtin fallback'))
    result = ws.fetch_document(db, 'https://1.1.1.1/guide')
    assert len(result.text) > 8000 and result.text.startswith('***') and result.partial
