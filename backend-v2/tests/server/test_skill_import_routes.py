import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from tests.domain.test_skill_imports import archive, skill
from zhishi.agent.runtime import AgentRuntime
from zhishi.agent.tools.skill_tools import import_skill, inspect_skill_import, read_skill_file
from zhishi.domain.models import AISkill
from zhishi.server.app import create_app


def test_manual_upload_directory_download_edit_and_restart(tmp_path):
    data = archive({'report/SKILL.md': skill(), 'report/assets/template.bin': b'\0\xfftemplate'})
    with TestClient(create_app(data_dir=tmp_path)) as client:
        response = client.post('/ai/skills/import/upload', files={'files': ('skill.zip', data)})
        assert response.status_code == 200, response.text
        sid = response.json()['skill_id']
        files = client.get(f'/ai/skills/{sid}').json()['files']
        assert len(files) == 2
        download = client.get(f'/ai/skills/{sid}/files', params={'path': 'assets/template.bin'})
        assert download.content == b'\0\xfftemplate' and 'attachment' in download.headers['content-disposition']
        assert client.get(f'/ai/skills/{sid}/files', params={'path': '../outside'}).status_code == 422
        assert client.post('/ai/skills/import/upload', files={'files': ('skill.zip', data)}).json()['status'] == 'already_imported'
        response = client.post('/ai/skills/import/upload', files=[
            ('files', ('local/SKILL.md', skill('local'))), ('files', ('local/references/rules.md', b'rules'))])
        assert response.json()['name'] == 'local'
    with TestClient(create_app(data_dir=tmp_path)) as client:
        assert client.get(f'/ai/skills/{sid}').json()['files'] == files


def test_attachment_routes_and_ai_tools_import_without_document_parser(tmp_path):
    data = archive({'weekly/SKILL.md': skill(), 'weekly/references/rules.md': b'Facts only.',
                    'other/SKILL.md': skill('other')})
    with TestClient(create_app(data_dir=tmp_path)) as client:
        response = client.post('/ai/attachments', files={'file': ('skills.zip', data)})
        assert response.status_code == 201 and response.json()['kind'] == 'skill_package'
        fid = response.json()['file_id']
        with client.app.state.session_factory() as db:
            ctx = SimpleNamespace(deps=SimpleNamespace(storage_root=client.app.state.storage_root))
            inspected = json.loads(inspect_skill_import(db, file_id=fid, ctx=ctx))
            assert len(inspected['candidates']) == 2
            before = db.query(AISkill).count()
            assert json.loads(import_skill(db, file_id=fid, ctx=ctx))['status'] == 'select_skill'
            assert db.query(AISkill).count() == before
            result = json.loads(import_skill(db, file_id=fid, skill_path='weekly/SKILL.md', ctx=ctx))
            assert result['status'] == 'imported'
            loaded = json.loads(read_skill_file(db, result['skill_id'], 'references/rules.md'))
            assert loaded['text'] == 'Facts only.'
            text, meta, _ = AgentRuntime(None, db, storage_root=client.app.state.storage_root)._attachment_blocks(db, [fid], {})
            assert 'import_skill' in text and meta[0]['id'] == fid


def test_github_endpoint_multi_selection_and_invalid_upload(tmp_path, monkeypatch):
    from zhishi.adapters import github_skills
    monkeypatch.setattr(github_skills, 'fetch', lambda *_: ({'a/SKILL.md': skill('a'), 'b/SKILL.md': skill('b')}, 'https://github.com/acme/example/tree/abc'))
    with TestClient(create_app(data_dir=tmp_path)) as client:
        body = {'url': 'https://github.com/acme/example'}
        result = client.post('/ai/skills/import/github', json=body).json()
        assert result['status'] == 'select_skill' and len(result['candidates']) == 2
        result = client.post('/ai/skills/import/github', json={**body, 'skill_path': 'b/SKILL.md'}).json()
        assert result['status'] == 'imported' and result['name'] == 'b'
        assert client.post('/ai/skills/import/upload', files={'files': ('SKILL.md', b'bad')}).status_code == 422
