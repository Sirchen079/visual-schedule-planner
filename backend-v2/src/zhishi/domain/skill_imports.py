"""Import standard SKILL.md packages without extracting or running their files."""
from __future__ import annotations

import hashlib
import io
import json
import re
import stat
import tarfile
import zipfile
from pathlib import PurePosixPath

import yaml
from sqlalchemy import select

from zhishi.domain import skills
from zhishi.domain.models import AISkill, AISkillPackage

MAX_UPLOAD = 20 * 1024 * 1024
MAX_EXPANDED = 50 * 1024 * 1024
MAX_ENTRIES = 2000
MAX_SKILL_FILES = 200
ARCHIVE_SUFFIXES = ('.zip', '.skill', '.tar', '.tar.gz', '.tgz')


def safe_path(value: str) -> str:
    if (not value or len(value) > 500 or value.startswith('/') or '\\' in value
            or ':' in value or any(ord(c) < 32 for c in value)
            or any(part in ('', '.', '..') for part in value.split('/'))):
        raise ValueError('技能包包含无效或越界路径。')
    return value


def _add(files: dict[str, bytes], path: str, data: bytes) -> None:
    safe_path(path)
    if path.casefold() in {name.casefold() for name in files}:
        raise ValueError(f'技能包包含重复路径：{path}')
    if len(files) >= MAX_ENTRIES or sum(map(len, files.values())) + len(data) > MAX_EXPANDED:
        raise ValueError('技能包最多 2000 个文件，解压后合计最多 50 MB。')
    files[path] = data


def unpack(filename: str, data: bytes, *, skill_scope: str | None = None) -> dict[str, bytes]:
    if len(data) > MAX_UPLOAD:
        raise ValueError('上传文件最多 20 MB。')
    files: dict[str, bytes] = {}
    try:
        if filename.lower().endswith(('.zip', '.skill')):
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                entries = archive.infolist()
                if len(entries) > MAX_ENTRIES or sum(e.file_size for e in entries) > MAX_EXPANDED:
                    raise ValueError('技能包超过 2000 个条目或解压后 50 MB 上限。')
                prefixes = None
                if skill_scope is not None:
                    # GitHub archives include unrelated repository files, including
                    # editor symlinks. Only retain folders that contain skills.
                    roots = {entry.filename.split('/')[0] for entry in entries}
                    if len(roots) != 1:
                        raise ValueError('GitHub 仓库压缩包结构不正确。')
                    root = next(iter(roots)) + '/'
                    scope = root + (safe_path(skill_scope) + '/' if skill_scope else '')
                    prefixes = [entry.filename[:-len('SKILL.md')] for entry in entries
                                if entry.filename.startswith(scope)
                                and PurePosixPath(entry.filename).name == 'SKILL.md']
                    if not prefixes:
                        raise ValueError('指定目录未找到 SKILL.md；请检查目录或完整分支 ref。')
                for entry in entries:
                    safe_path(entry.orig_filename.rstrip('/') if entry.is_dir() else entry.orig_filename)
                    safe_path(entry.filename.rstrip('/') if entry.is_dir() else entry.filename)
                    if prefixes is not None and not any(entry.filename.startswith(prefix) for prefix in prefixes):
                        continue
                    mode = entry.external_attr >> 16
                    if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                        raise ValueError('技能包不支持符号链接或特殊文件。')
                    if not entry.is_dir():
                        _add(files, entry.filename, archive.read(entry))
        elif filename.lower().endswith(('.tar', '.tar.gz', '.tgz')):
            with tarfile.open(fileobj=io.BytesIO(data), mode='r:*') as archive:
                total = 0
                for count, entry in enumerate(archive, 1):
                    total += entry.size
                    if count > MAX_ENTRIES or total > MAX_EXPANDED:
                        raise ValueError('技能包超过条目数或解压大小上限。')
                    path = entry.name.removeprefix('./').rstrip('/')
                    if not path and entry.isdir():
                        continue
                    safe_path(path)
                    if entry.isdir():
                        continue
                    if not entry.isfile():
                        raise ValueError('技能包不支持符号链接、硬链接或特殊文件。')
                    stream = archive.extractfile(entry)
                    if stream is None:
                        raise ValueError('压缩包文件无法读取。')
                    _add(files, path, stream.read(MAX_EXPANDED + 1))
        elif filename.lower().endswith('.md'):
            _add(files, 'SKILL.md', data)
        else:
            raise ValueError('请选择 SKILL.md、ZIP/.skill 或 TAR/TAR.GZ/TGZ；其他格式请先转换。')
    except (zipfile.BadZipFile, tarfile.TarError, RuntimeError, EOFError, OSError) as exc:
        raise ValueError('压缩包损坏、加密或使用了不支持的压缩方式。') from exc
    return files


def parse_skill(data: bytes) -> tuple[dict, str]:
    if len(data) > 200000:
        raise ValueError('SKILL.md 过大；请将长资料放入 references/。')
    try:
        text = data.decode('utf-8-sig').replace('\r\n', '\n')
    except UnicodeDecodeError as exc:
        raise ValueError('SKILL.md 必须使用 UTF-8 编码。') from exc
    match = re.match(r'\A---\s*\n(.*?)\n---[ \t]*(?:\n|$)(.*)\Z', text, re.DOTALL)
    if not match:
        raise ValueError('SKILL.md 须包含 YAML 头部的 name、description 和 Markdown 正文。')
    header, body = match.groups()
    if len(header) > 16000:
        raise ValueError('技能元数据过大。')
    try:
        if any(isinstance(token, (yaml.AliasToken, yaml.AnchorToken)) for token in yaml.scan(header)):
            raise ValueError('技能元数据不支持 YAML 锚点和别名。')
        metadata = yaml.safe_load(header)
    except (yaml.YAMLError, RecursionError) as exc:
        raise ValueError('技能 YAML 头部格式不正确。') from exc
    if not isinstance(metadata, dict) or not all(isinstance(metadata.get(k), str) for k in ('name', 'description')):
        raise ValueError('技能 name 和 description 必须是非空字符串。')
    skills.validate(metadata['name'], metadata['description'], body)
    return metadata, body.strip()


def candidates(files: dict[str, bytes]) -> list[dict]:
    found = []
    for path, data in sorted(files.items()):
        if PurePosixPath(path).name != 'SKILL.md':
            continue
        try:
            meta, _ = parse_skill(data)
            found.append({'path': path, 'name': meta['name'], 'description': meta['description'], 'error': ''})
        except ValueError as exc:
            found.append({'path': path, 'name': PurePosixPath(path).parent.name or 'SKILL.md',
                          'description': '', 'error': str(exc)})
    if not found:
        raise ValueError('未找到 SKILL.md；请上传技能文件或包含它的目录/压缩包。')
    if len(found) > 100:
        raise ValueError('包内超过 100 个技能；请指定较小的目录或拆分上传。')
    return found


def select_package(files: dict[str, bytes], skill_path: str = '') -> tuple[dict | None, list[dict]]:
    choices = candidates(files)
    if not skill_path and len(choices) != 1:
        return None, choices
    path = safe_path(skill_path) if skill_path else choices[0]['path']
    if not any(choice['path'] == path for choice in choices):
        raise ValueError('skill_path 必须是候选列表中的 SKILL.md 路径。')
    metadata, body = parse_skill(files[path])
    prefix = path[:-len('SKILL.md')]
    nested = [c['path'][:-len('SKILL.md')] for c in choices if c['path'] != path and c['path'].startswith(prefix)]
    selected = {name[len(prefix):]: data for name, data in files.items()
                if name.startswith(prefix) and not any(name.startswith(folder) for folder in nested)}
    if len(selected) > MAX_SKILL_FILES or sum(map(len, selected.values())) > MAX_UPLOAD:
        raise ValueError('单个技能最多 200 个文件、合计 20 MB；请移除无关文件。')
    warnings = []
    if len(selected) == 1:
        warnings.append('仅导入 SKILL.md；若正文引用其他文件，请改用完整技能目录或压缩包。')
    if any(name.startswith('scripts/') for name in selected):
        warnings.append('脚本已保留供查看和下载；导入不会安装依赖或执行脚本。')
    return {'metadata': metadata, 'content': body, 'files': selected, 'warnings': warnings}, choices


def _archive(files: dict[str, bytes]) -> tuple[bytes, str, str]:
    stream, digest, manifest = io.BytesIO(), hashlib.sha256(), []
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path, data in sorted(files.items()):
            safe_path(path)
            archive.writestr(zipfile.ZipInfo(path, (1980, 1, 1, 0, 0, 0)), data,
                             compress_type=zipfile.ZIP_DEFLATED)
            digest.update(path.encode() + b'\0' + hashlib.sha256(data).digest())
            try:
                data.decode('utf-8-sig')
                text = b'\0' not in data
            except UnicodeDecodeError:
                text = False
            manifest.append({'path': path, 'size': len(data), 'is_text': text})
    return stream.getvalue(), digest.hexdigest(), json.dumps(manifest, ensure_ascii=False)


def import_package(db, files: dict[str, bytes], *, source: str, skill_path: str = '',
                   name: str | None = None, enabled: bool = True) -> dict:
    package, choices = select_package(files, skill_path)
    if package is None:
        return {'status': 'select_skill', 'candidates': choices, 'warnings': [], 'skill_id': None}
    meta = package['metadata']
    target_name = name.strip() if name is not None else meta['name'].strip()
    skills.validate(target_name, meta['description'], package['content'])
    # Honor the source's explicit-only policy by importing it disabled.
    policy = package['files'].get('agents/openai.yaml', b'')
    if policy:
        try:
            policy_text = policy.decode('utf-8-sig')
            if len(policy_text) > 16000 or any(isinstance(t, (yaml.AliasToken, yaml.AnchorToken)) for t in yaml.scan(policy_text)):
                raise ValueError('agents/openai.yaml 过大或包含 YAML 锚点。')
            settings = yaml.safe_load(policy_text)
        except (UnicodeDecodeError, yaml.YAMLError, RecursionError) as exc:
            raise ValueError('agents/openai.yaml 格式不正确。') from exc
        if isinstance(settings, dict) and isinstance(settings.get('policy'), dict) and settings['policy'].get('allow_implicit_invocation') is False:
            enabled = False
            package['warnings'].append('来源设置了禁止自动调用，已导入为停用；可在设置中自行启用。')
    archive, fingerprint, manifest = _archive(package['files'])
    db.connection().exec_driver_sql('UPDATE ai_skills SET id = id WHERE 0')
    existing = db.scalar(select(AISkill).where(AISkill.name == target_name))
    if existing:
        stored = db.get(AISkillPackage, existing.id, populate_existing=True)
        if (not existing.is_builtin and stored and stored.fingerprint == fingerprint
                and existing.description == meta['description'].strip() and existing.content == package['content']):
            return {'status': 'already_imported', 'skill_id': existing.id, 'name': existing.name,
                    'enabled': existing.enabled, 'warnings': package['warnings'], 'candidates': []}
        raise skills.SkillConflict(f'已有同名技能「{target_name}」，未覆盖；请填写新名称后导入。')
    row = skills.write(db, name=target_name, description=meta['description'], content=package['content'], enabled=enabled)
    db.add(AISkillPackage(skill_id=row.id, archive=archive, fingerprint=fingerprint,
                          manifest_json=manifest, source=source))
    db.flush()
    return {'status': 'imported', 'skill_id': row.id, 'name': row.name, 'enabled': row.enabled,
            'warnings': package['warnings'], 'candidates': []}


def file_bytes(db, skill_id: int, path: str, *, enabled_only: bool = False) -> bytes:
    skills.get(db, skill_id, enabled_only=enabled_only)
    safe_path(path)
    package = db.get(AISkillPackage, skill_id, populate_existing=True)
    if package is None:
        raise LookupError('该技能没有导入文件。')
    with zipfile.ZipFile(io.BytesIO(package.archive)) as archive:
        try:
            return archive.read(path)
        except KeyError as exc:
            raise LookupError('技能文件不存在；请按 read_skill 返回的 files 路径读取。') from exc


def sync_entrypoint(db, row) -> None:
    package = db.get(AISkillPackage, row.id)
    if package is None:
        return
    with zipfile.ZipFile(io.BytesIO(package.archive)) as archive:
        files = {entry.filename: archive.read(entry) for entry in archive.infolist()}
    metadata, _ = parse_skill(files['SKILL.md'])
    metadata.update(name=row.name, description=row.description)
    files['SKILL.md'] = ('---\n' + yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False)
                         + '---\n\n' + row.content + '\n').encode()
    package.archive, package.fingerprint, package.manifest_json = _archive(files)
