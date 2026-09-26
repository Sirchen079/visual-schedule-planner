"""Public GitHub skill imports pinned to a commit, using bounded HTTPS downloads.

API contract: https://docs.github.com/en/rest/repos/contents#download-a-repository-archive-zip
"""
from __future__ import annotations

import json
import re
from urllib.parse import quote, unquote, urljoin, urlsplit

import httpx

from zhishi.adapters.web import _validate_public_url
from zhishi.domain.skill_imports import MAX_UPLOAD, safe_path, unpack

ALLOWED_HOSTS = {'api.github.com', 'codeload.github.com', 'github.com', 'raw.githubusercontent.com'}


def validate_url(url: str) -> str:
    parts = urlsplit(url)
    if (parts.scheme != 'https' or parts.hostname not in ALLOWED_HOSTS
            or parts.username or parts.password or parts.port not in (None, 443)):
        raise ValueError('仅支持公开 GitHub 仓库的 HTTPS 链接，不接受凭据或其他站点。')
    return _validate_public_url(url)


def _download(client: httpx.Client, url: str, limit: int = MAX_UPLOAD) -> bytes:
    current = url
    for _ in range(6):
        validate_url(current)
        with client.stream('GET', current, follow_redirects=False,
                           headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'Zhishi-Skill-Import'}) as response:
            if response.is_redirect:
                location = response.headers.get('location')
                if not location:
                    raise ValueError('GitHub 重定向缺少目标地址。')
                current = urljoin(current, location)
                continue
            if response.status_code == 404:
                raise ValueError('仓库、分支或路径不存在，或仓库为私有；私有技能请下载后上传。')
            if response.status_code in (403, 429):
                raise ValueError('GitHub 暂时限流或拒绝访问，请稍后重试，也可上传下载好的技能包。')
            if response.status_code >= 400:
                raise ValueError(f'GitHub 下载失败（HTTP {response.status_code}）。')
            chunks, total = [], 0
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > limit:
                    raise ValueError('GitHub 响应超过大小上限，请仅打包需要的技能目录上传。')
                chunks.append(chunk)
            return b''.join(chunks)
    raise ValueError('GitHub 重定向次数过多。')


def fetch(url: str, ref: str | None = None, *, client: httpx.Client | None = None) -> tuple[dict[str, bytes], str]:
    if len(url) > 2000:
        raise ValueError('GitHub 链接过长。')
    validate_url(url)
    parsed = urlsplit(url)
    parts = unquote(parsed.path).strip('/').split('/')
    if len(parts) < 2 or not all(re.fullmatch(r'[A-Za-z0-9_.-]+', p) for p in parts[:2]):
        raise ValueError('请输入 GitHub 仓库、技能目录或 SKILL.md 链接。')
    owner, repo = parts[0], parts[1].removesuffix('.git')
    if owner in ('.', '..') or repo in ('', '.', '..'):
        raise ValueError('GitHub 仓库名称无效。')
    suffix, path = '', ''
    if parsed.hostname == 'raw.githubusercontent.com':
        suffix = '/'.join(parts[2:])
    elif parsed.hostname == 'github.com' and len(parts) > 2:
        if parts[2] not in ('tree', 'blob'):
            raise ValueError('请使用仓库首页、tree 目录或 blob/SKILL.md 链接。')
        suffix = '/'.join(parts[3:])
    elif parsed.hostname != 'github.com':
        raise ValueError('请提供 github.com 的仓库链接或 raw.githubusercontent.com 的 SKILL.md 链接。')
    if suffix:
        chosen_ref = ref or suffix.split('/')[0]
        if suffix != chosen_ref and not suffix.startswith(chosen_ref + '/'):
            raise ValueError('ref 与链接中的分支不一致。带斜杠分支请填写完整 ref。')
        path = suffix[len(chosen_ref):].strip('/')
        ref = chosen_ref
    if path:
        safe_path(path)
        if path.endswith('/SKILL.md') or path == 'SKILL.md':
            path = path[:-len('SKILL.md')].rstrip('/')
        elif parsed.hostname == 'raw.githubusercontent.com' or (len(parts) > 2 and parts[2] == 'blob'):
            raise ValueError('单文件链接必须指向 SKILL.md。')
    base = f'https://api.github.com/repos/{owner}/{repo}'
    owned = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(30, connect=10), trust_env=False)
    try:
        if not ref:
            metadata = json.loads(_download(client, base, 1000000))
            ref = metadata.get('default_branch')
        if not isinstance(ref, str) or not ref or len(ref) > 200:
            raise ValueError('无法确定仓库分支。')
        commit = json.loads(_download(client, f'{base}/commits/{quote(ref, safe="")}', 2000000))
        sha = commit.get('sha')
        if not isinstance(sha, str) or not re.fullmatch(r'[0-9a-fA-F]{40}', sha):
            raise ValueError('GitHub 未返回有效的提交版本。')
        files = unpack('github.zip', _download(client, f'{base}/zipball/{sha}'), skill_scope=path)
        roots = {name.split('/')[0] for name in files}
        if len(roots) != 1 or not all('/' in name for name in files):
            raise ValueError('GitHub 仓库压缩包结构不正确。')
        files = {name.split('/', 1)[1]: data for name, data in files.items()}
        if path:
            files = {name: data for name, data in files.items() if name.startswith(path + '/')}
            if not files:
                raise ValueError('指定的技能目录不存在；带斜杠分支请显式传完整 ref。')
        return files, f'https://github.com/{owner}/{repo}/tree/{sha}' + (f'/{path}' if path else '')
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        raise ValueError('GitHub 连接或响应异常，请重试或上传技能压缩包。') from exc
    finally:
        if owned:
            client.close()
