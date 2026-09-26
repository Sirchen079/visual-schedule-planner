import io
import json
import stat
import tarfile
import zipfile

import pytest

from zhishi.agent.tools.skill_tools import read_skill_file
from zhishi.domain import skill_imports as imports
from zhishi.domain import skills
from zhishi.domain.models import AISkill, AISkillPackage


def skill(name='weekly-report'):
    return f'---\nname: {name}\ndescription: >\n  Write weekly reports.\nmetadata:\n  author: Example\n---\n\nRead references/rules.md and report concrete progress.\n'.encode()


def archive(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as output:
        for name, data in files.items():
            entry = zipfile.ZipInfo()
            entry.filename = name
            output.writestr(entry, data)
    return stream.getvalue()


def test_import_preserves_files_repeat_disable_edit_and_delete(db):
    binary = b'\x00\xfftemplate-data'
    files = imports.unpack('skill.zip', archive({'bundle/SKILL.md': skill(),
        'bundle/references/rules.md': b'Check facts. ' * 1000,
        'bundle/scripts/helper.py': b'raise RuntimeError("NEVER RUN")',
        'bundle/assets/template.bin': binary}))
    result = imports.import_package(db, files, source='upload')
    db.commit()
    sid = result['skill_id']
    detail = skills.detail(db, sid)
    assert detail['source'] == 'upload' and len(detail['files']) == 4
    assert imports.file_bytes(db, sid, 'assets/template.bin') == binary
    first = json.loads(read_skill_file(db, sid, 'references/rules.md'))
    second = json.loads(read_skill_file(db, **first['next_call']['args']))
    third = json.loads(read_skill_file(db, **second['next_call']['args']))
    assert first['text'] + second['text'] + third['text'] == ('Check facts. ' * 1000)
    assert third['next_call'] is None
    assert json.loads(read_skill_file(db, sid, 'assets/template.bin'))['binary'] is True
    row = skills.get(db, sid)
    original = imports.file_bytes(db, sid, 'SKILL.md')
    skills.write(db, skill_id=sid, expected_revision=skills.revision(db, row), name=row.name,
                 description=row.description, content=row.content, enabled=False)
    db.commit()
    assert imports.file_bytes(db, sid, 'SKILL.md') == original
    again = imports.import_package(db, files, source='same upload')
    db.commit()
    assert again['status'] == 'already_imported' and again['enabled'] is False
    assert db.query(AISkill).count() == 1
    with pytest.raises(LookupError):
        read_skill_file(db, sid, 'scripts/helper.py')
    skills.write(db, skill_id=sid, expected_revision=skills.revision(db, row), name=row.name,
                 description=row.description, content='New procedure.', enabled=True)
    db.commit()
    metadata, body = imports.parse_skill(imports.file_bytes(db, sid, 'SKILL.md'))
    assert body == 'New procedure.' and metadata['metadata']['author'] == 'Example'
    assert imports.file_bytes(db, sid, 'assets/template.bin') == binary
    with pytest.raises(skills.SkillConflict):
        imports.import_package(db, files, source='old upload')
    db.rollback()
    db.delete(skills.get(db, sid))
    db.commit()
    assert db.query(AISkillPackage).count() == 0


def test_multiple_skills_require_selection_and_do_not_import_nested_skills(db):
    files = {'repo/SKILL.md': skill('root'), 'repo/nested/SKILL.md': skill('nested'),
             'repo/nested/references/x.md': b'inner', 'repo/LICENSE': b'MIT'}
    result = imports.import_package(db, files, source='repo')
    assert result['status'] == 'select_skill' and len(result['candidates']) == 2
    assert db.query(AISkill).count() == 0
    result = imports.import_package(db, files, source='repo', skill_path='repo/SKILL.md')
    db.commit()
    assert [file['path'] for file in skills.detail(db, result['skill_id'])['files']] == ['LICENSE', 'SKILL.md']
    with pytest.raises(ValueError):
        imports.import_package(db, files, source='repo', skill_path='missing/SKILL.md')


def test_tar_and_explicit_only_policy(db):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w:gz') as output:
        for name, data in {'./report/SKILL.md': skill(),
                           './report/agents/openai.yaml': b'policy:\n  allow_implicit_invocation: false\n'}.items():
            entry = tarfile.TarInfo(name); entry.size = len(data)
            output.addfile(entry, io.BytesIO(data))
    files = imports.unpack('report.tgz', stream.getvalue())
    result = imports.import_package(db, files, source='upload')
    db.commit()
    assert result['enabled'] is False and result['warnings']


@pytest.mark.parametrize('path', ['../outside', '/absolute', 'C:/outside', 'dir\\outside', 'dir/../outside'])
def test_reject_archive_paths_without_writing_to_disk(path):
    with pytest.raises(ValueError, match='路径'):
        imports.unpack('bad.zip', archive({'SKILL.md': skill(), path: b'bad'}))


def test_reject_symlinks_duplicates_bombs_and_bad_metadata(monkeypatch):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as output:
        entry = zipfile.ZipInfo('link'); entry.external_attr = (stat.S_IFLNK | 0o777) << 16
        output.writestr(entry, '../private')
    with pytest.raises(ValueError, match='链接'):
        imports.unpack('bad.zip', stream.getvalue())
    with pytest.raises(ValueError, match='重复'):
        imports.unpack('bad.zip', archive({'A.md': b'one', 'a.md': b'two'}))
    with pytest.raises(ValueError):
        imports.parse_skill(b'---\nname: a\ndescription: &x [*x]\n---\nbody')
    with pytest.raises(ValueError):
        imports.parse_skill(b'---\nname: a\n---\nbody')
    with pytest.raises(ValueError):
        imports.unpack('bad.zip', b'corrupt')
    monkeypatch.setattr(imports, 'MAX_EXPANDED', 100)
    with pytest.raises(ValueError, match='上限'):
        imports.unpack('bomb.zip', archive({'SKILL.md': b'a' * 101}))


def test_name_conflict_requires_explicit_rename(db):
    imports.import_package(db, {'SKILL.md': skill()}, source='first')
    db.commit()
    other = {'SKILL.md': skill() + b'New content.'}
    with pytest.raises(skills.SkillConflict):
        imports.import_package(db, other, source='second')
    db.rollback()
    result = imports.import_package(db, other, source='second', name='weekly-report-2')
    db.commit()
    assert result['name'] == 'weekly-report-2' and db.query(AISkill).count() == 2


def test_github_scope_skips_unrelated_repository_links_but_rejects_skill_links():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as output:
        output.writestr('repo/skills/report/SKILL.md', skill())
        entry = zipfile.ZipInfo('repo/.agents/report')
        entry.external_attr = (stat.S_IFLNK | 0o777) << 16
        output.writestr(entry, '../skills/report')
    selected = imports.unpack('repo.zip', stream.getvalue(), skill_scope='skills/report')
    assert list(selected) == ['repo/skills/report/SKILL.md']
    with zipfile.ZipFile(stream, 'a') as output:
        entry = zipfile.ZipInfo('repo/skills/report/external')
        entry.external_attr = (stat.S_IFLNK | 0o777) << 16
        output.writestr(entry, '/private')
    with pytest.raises(ValueError, match='链接'):
        imports.unpack('repo.zip', stream.getvalue(), skill_scope='skills/report')
