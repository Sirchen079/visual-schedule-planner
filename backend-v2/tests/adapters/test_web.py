"""web 工具适配器：Bing RSS 检索 / 正文提取 / SSRF 双重校验。
httpx MockTransport 全程无真实网络（DNS 校验仅解析公网样例域）。"""
import httpx

from zhishi.adapters import web


def test_search_bing_rss():
    rss = '''<?xml version="1.0"?><rss><channel><item>
      <title>智谱 AI 官网</title><link>https://z.ai</link><description>智谱</description>
    </item></channel></rss>'''
    transport = httpx.MockTransport(lambda req: httpx.Response(200, text=rss))
    hits = web.search("智谱", client=httpx.Client(transport=transport))
    assert hits[0]["title"] == "智谱 AI 官网" and hits[0]["url"] == "https://z.ai"


def test_fetch_extracts_main_text_and_caps():
    html = "<html><body><script>bad()</script><h1>标题</h1><p>" + "正文" * 50 + "</p></body></html>"
    transport = httpx.MockTransport(lambda req: httpx.Response(200, text=html, headers={'content-type':'text/html; charset=utf-8'}))
    out = web.fetch("https://example.com/a", client=httpx.Client(transport=transport))
    assert "标题" in out and "bad" not in out and len(out) <= web.MAX_CHARS + 100


def test_ssrf_blocked():
    import pytest
    for url in ("http://127.0.0.1/x", "http://169.254.169.254/latest/meta-data",
                "http://[::1]/x", "file:///etc/passwd", "ftp://x", "http://10.0.0.1/x"):
        with pytest.raises(ValueError):
            web.fetch(url)   # 抛错于发起请求前（解析+公网校验）


def test_redirect_revalidation():
    # 第一跳 302 → 内网地址：重定向后必须重新公网校验并拒绝
    def handler(req):
        if req.url.host == "public.example.com":
            return httpx.Response(302, headers={"Location": "http://192.168.1.1/inner"})
        return httpx.Response(200, text="inner")
    transport = httpx.MockTransport(handler)
    import pytest
    with pytest.raises(ValueError):
        web.fetch("http://public.example.com/a", client=httpx.Client(transport=transport))


def test_redirect_revalidation_ip_literal():
    """补充：公网 IP 字面量首跳 302 → 内网（不经 DNS，真正命中重定向重校验路径）。"""
    import pytest

    def handler(req):
        if req.url.host == "1.1.1.1":
            return httpx.Response(302, headers={"Location": "http://192.168.1.1/inner"})
        return httpx.Response(200, text="inner")

    transport = httpx.MockTransport(handler)
    with pytest.raises(ValueError):
        web.fetch("http://1.1.1.1/a", client=httpx.Client(transport=transport))


def test_search_error_returns_error_entry_not_raise():
    """检索异常不外抛：返回 [{"error": ...}]（模型可读的失败语义）。"""
    transport = httpx.MockTransport(lambda req: httpx.Response(500, text="boom"))
    hits = web.search("x", client=httpx.Client(transport=transport))
    assert len(hits) == 1 and "error" in hits[0]


def test_search_follows_regional_redirect_and_blocks_private_hop(monkeypatch):
    import socket
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [(socket.AF_INET, 1, 6, '', ('1.1.1.1', 0))])
    seen = []
    def handler(req):
        seen.append(req.url.host)
        if req.url.host == 'www.bing.com':
            return httpx.Response(302, headers={'Location':'https://cn.bing.com/search?format=rss&q=test'})
        return httpx.Response(200, text='<rss><channel><item><title>Tutorial</title><link>https://example.org</link></item></channel></rss>')
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert web.search('test', client=client)[0]['title'] == 'Tutorial'
    assert seen == ['www.bing.com', 'cn.bing.com']
    seen.clear()
    def private(req):
        seen.append(req.url.host)
        return httpx.Response(302, headers={'Location':'http://127.0.0.1/private'})
    with httpx.Client(transport=httpx.MockTransport(private)) as client:
        assert '非公网' in web.search('test', client=client)[0]['error']
    assert seen == ['www.bing.com']


def test_search_redirect_loop_and_oversized_response(monkeypatch):
    monkeypatch.setattr(web, '_validate_public_url', lambda url: url)
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(302, headers={'Location':'/search'}))) as client:
        assert '重定向超过' in web.search('test', client=client)[0]['error']
    monkeypatch.setattr(web, 'MAX_BYTES', 10)
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, text='x' * 100))) as client:
        assert '超过2MB' in web.search('test', client=client)[0]['error']


def test_web_tools_registered():
    """web_search / web_fetch 注册为 readonly，供计划模式和研究子代理使用。"""
    import zhishi.agent.tools.web_tools  # noqa: F401 触发自注册（生产路径由 runtime 导入）
    from zhishi.agent.tools.registry import get_spec
    for name in ("web_search", "web_fetch"):
        spec = get_spec(name)
        assert spec is not None and spec.safety == "readonly" and callable(spec.fn)
        assert spec.feature_flag is None
