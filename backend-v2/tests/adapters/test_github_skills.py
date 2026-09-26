import httpx
import pytest

from tests.domain.test_skill_imports import archive, skill
from zhishi.adapters import github_skills as github

SHA = 'a' * 40


@pytest.mark.parametrize('url,ref', [
    ('https://github.com/acme/reports/tree/main/skills/weekly', None),
    ('https://github.com/acme/reports/blob/main/skills/weekly/SKILL.md', None),
    ('https://raw.githubusercontent.com/acme/reports/main/skills/weekly/SKILL.md', None),
    ('https://github.com/acme/reports/tree/feature/docs/skills/weekly', 'feature/docs'),
    ('https://github.com/acme/reports', None),
])
def test_resolves_default_branch_or_path_and_pins_download(monkeypatch, url, ref):
    monkeypatch.setattr(github, '_validate_public_url', lambda value: value)
    seen = []
    def handle(request):
        seen.append(str(request.url))
        if request.url.path.endswith('/repos/acme/reports'):
            return httpx.Response(200, json={'default_branch': 'main'})
        if '/commits/' in request.url.path:
            return httpx.Response(200, json={'sha': SHA})
        if '/zipball/' in request.url.path:
            assert request.url.path.endswith(SHA)
            return httpx.Response(302, headers={'location': f'https://codeload.github.com/acme/reports/legacy.zip/{SHA}'})
        return httpx.Response(200, content=archive({'root/skills/weekly/SKILL.md': skill(),
            'root/skills/weekly/references/rules.md': b'rules', 'root/README.md': b'project'}))
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        files, source = github.fetch(url, ref, client=client)
    assert 'skills/weekly/SKILL.md' in files and SHA in source
    if '/skills/weekly' in url:
        assert 'README.md' not in files
    assert any('/zipball/' + SHA in item for item in seen)


@pytest.mark.parametrize('url', ['http://github.com/a/b', 'https://github.com.evil.test/a/b',
                               'https://user:password@github.com/a/b', 'https://127.0.0.1/a/b'])
def test_rejects_non_github_and_credentials_before_connect(url):
    with pytest.raises(ValueError):
        github.fetch(url)


def test_redirect_cannot_leave_allowlist_and_private_repo_errors_are_clear(monkeypatch):
    monkeypatch.setattr(github, '_validate_public_url', lambda value: value)
    with (httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(302, headers={'location': 'https://127.0.0.1/secrets'}))) as client,
          pytest.raises(ValueError, match='GitHub')):
        github.fetch('https://github.com/acme/reports', client=client)
    with (httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(404))) as client,
          pytest.raises(ValueError, match='私有')):
        github.fetch('https://github.com/acme/reports', client=client)
