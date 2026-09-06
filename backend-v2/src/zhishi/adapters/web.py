"""web_search / web_fetch 适配器（无浏览器依赖）。
SSRF 双重校验：请求前做「scheme 白名单 + host 解析 + 公网 IP 校验」，
重定向每一跳重新走同一校验（手动跟随重定向，杜绝 302 跳内网）。
独立 client 参数供测试注入 MockTransport；默认 client 15s 超时。"""
from __future__ import annotations

from dataclasses import dataclass, field

import httpx

MAX_CHARS = 8000          # 正文截断上限
MAX_BYTES = 2 * 1024 * 1024   # 下载上限 2MB（stream + 计数）
MAX_REDIRECTS = 5
MAX_DOCUMENT_CHARS = 500_000


@dataclass
class WebDocument:
    text: str
    partial: bool = False
    warnings: list[str] = field(default_factory=list)

_UA = {"User-Agent": (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")}


def _default_client() -> httpx.Client:
    return httpx.Client(timeout=15)


def _validate_public_url(url: str) -> str:
    """校验并返回规范化 URL：非 http(s) / 无 host / 解析出内网·环回·链路本地·
    保留段地址 → ValueError（在发起任何请求前抛出）。"""
    from urllib.parse import urlparse
    parts = urlparse(url)
    if parts.scheme not in ("http", "https"):
        raise ValueError(f"仅允许 http(s) 地址，拒绝 {parts.scheme or '空'} scheme")
    host = parts.hostname
    if not host:
        raise ValueError("URL 缺少主机名")
    # IP 字面量快路径（含 IPv6，hostname 已去方括号）
    import ipaddress
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        if not ip.is_global:
            raise ValueError(f"禁止访问非公网地址：{host}")
        return url
    # 域名：先 getaddrinfo 解析，再逐个校验解析结果（DNS 解析失败视为不可达）
    import socket
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as exc:
        raise ValueError(f"域名无法解析：{host}（{exc.__class__.__name__}）") from exc
    for info in infos:
        try:
            resolved = ipaddress.ip_address(info[4][0])
        except ValueError:  # pragma: no cover - getaddrinfo 只返回地址
            continue
        if not resolved.is_global:
            raise ValueError(f"域名 {host} 解析到非公网地址，拒绝访问")
    return url


def search(query: str, limit: int = 5, client: httpx.Client | None = None) -> list[dict]:
    """Bing RSS 检索：返回 [{title, url, description}]（最多 limit 条）。
    任何异常返回 [{"error": "..."}]，不向外抛（工具层直接回给模型）。"""
    import xml.etree.ElementTree as ET
    from urllib.parse import quote, urljoin
    owned = client is None
    c = client or _default_client()
    try:
        current = _validate_public_url(f"https://www.bing.com/search?q={quote(query)}&format=rss")
        for _hop in range(MAX_REDIRECTS + 1):
            with c.stream('GET', current, headers=_UA, follow_redirects=False) as resp:
                if resp.is_redirect:
                    location = resp.headers.get('location')
                    if not location:
                        raise ValueError('搜索重定向缺少 Location')
                    current = _validate_public_url(urljoin(current, location))
                    continue
                resp.raise_for_status()
                chunks, total = [], 0
                for chunk in resp.iter_bytes():
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise ValueError('搜索响应超过2MB')
                    chunks.append(chunk)
                text = b''.join(chunks).decode(resp.charset_encoding or 'utf-8', errors='replace')
                break
        else:
            raise ValueError(f'搜索重定向超过 {MAX_REDIRECTS} 次')
        # 防 XML 实体扩展（billion laughs）：RSS 不应含 DTD/实体定义，出现即拒绝解析
        head = text[:2048].lower()
        if "<!doctype" in head or "<!entity" in head:
            raise ValueError("XML 含 DTD/实体定义，已拒绝解析")
        items = ET.fromstring(text).findall(".//item")[:max(1, limit)]
        return [{"title": (i.findtext("title") or "").strip(),
                 "url": (i.findtext("link") or "").strip(),
                 "description": (i.findtext("description") or "").strip()}
                for i in items]
    except Exception as exc:  # noqa: BLE001 -- search adapters return recoverable per-query failures.
        return [{"error": f"搜索失败：{str(exc)[:200]}"}]
    finally:
        if owned:
            c.close()


def fetch(url: str, client: httpx.Client | None = None) -> str:
    """Small preview for standalone web tools; research uses fetch_document."""
    return fetch_document(url, client).text[:MAX_CHARS]


def fetch_document(url: str, client: httpx.Client | None = None) -> WebDocument:
    """Bounded extracted page text with explicit truncation; never execute page scripts."""
    from urllib.parse import urljoin
    owned = client is None
    c = client or _default_client()
    try:
        current = _validate_public_url(url)
        status, chunks, warnings = 0, [], []
        for _hop in range(MAX_REDIRECTS + 1):
            with c.stream("GET", current, headers=_UA, follow_redirects=False) as r:
                if r.is_redirect:
                    loc = r.headers.get("location", "")
                    if not loc:
                        raise ValueError("重定向缺少 Location")
                    current = _validate_public_url(urljoin(current, loc))
                    continue
                status = r.status_code
                if status >= 400:
                    raise ValueError(f"HTTP {status}：{current}")
                content_type = r.headers.get('content-type', '').split(';')[0].strip().lower()
                if content_type and not (content_type.startswith('text/') or content_type in (
                        'application/xhtml+xml', 'application/json', 'application/xml')):
                    raise ValueError('该地址不是可读网页文本；PDF或其他文件请下载后上传到资料库')
                total = 0
                for chunk in r.iter_bytes():
                    remaining = MAX_BYTES - total
                    total += len(chunk)
                    if total > MAX_BYTES:
                        chunks.append(chunk[:remaining])
                        warnings.append('网页响应超过2MB，仅保存已下载部分；后续内容尚未读取。')
                        break
                    chunks.append(chunk)
                charset = r.charset_encoding or "utf-8"
                break
        else:
            raise ValueError(f"重定向超过 {MAX_REDIRECTS} 次")
        html = b"".join(chunks).decode(charset, errors="replace")
        text = html.strip() if content_type and content_type != 'text/html' and content_type != 'application/xhtml+xml' else _extract_text(html)
        if len(text) > MAX_DOCUMENT_CHARS:
            warnings.append(f'网页正文超过 {MAX_DOCUMENT_CHARS} 字符，仅保存前段；后续内容尚未读取。')
        # A static extraction cannot establish completeness of JS-rendered or paywalled content.
        warnings.append('保存的是本次响应中可提取的文本；动态加载、登录后内容和页面链接未自动读取。')
        return WebDocument(text[:MAX_DOCUMENT_CHARS], len(warnings) > 1, warnings)
    finally:
        if owned:
            c.close()


def _extract_text(html: str) -> str:
    """剥 script/style → 去标签 → 实体解码 → 压缩空白。"""
    import html as _html
    import re
    text = re.sub(r"(?is)<(script|style)\b[^>]*>.*?</\1\s*>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = _html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()
