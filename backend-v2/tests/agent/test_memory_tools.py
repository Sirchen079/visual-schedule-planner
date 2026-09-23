"""长期记忆：数据表 CRUD、四个 AI 工具（查重/上限/ModelRetry/检索）、registry 开关门控、
prompts 注入三档（关闭零注入 / 零记忆零注入 / 有记忆注入且截断）。"""
import pytest
from pydantic_ai.exceptions import ModelRetry

from zhishi.agent import prompts
from zhishi.agent.prompts import MEMORY_MORE_NOTE, MEMORY_PREFIX_CHARS
from zhishi.agent.tools.memory_tools import (forget_memory, memory_count, memory_enabled,
                                             save_memory, search_memory, update_memory)
from zhishi.agent.tools.registry import specs_for
from zhishi.domain import settingsvc
from zhishi.domain.models import AIMemory
from zhishi.infra.database import make_engine, make_session_factory, create_all

MEMORY_TOOLS = {'save_memory', 'update_memory', 'forget_memory', 'search_memory'}


@pytest.fixture
def db(tmp_path):
    engine = make_engine(tmp_path / "test.db")
    create_all(engine)
    session = make_session_factory(engine)()
    yield session
    session.close()
    engine.dispose()


def add_memory(db, content, kind='fact', keywords='', **kw) -> AIMemory:
    row = AIMemory(kind=kind, content=content, keywords=keywords, source='ai', **kw)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ---- 建表与 CRUD ----

def test_table_crud_and_roundtrip(db):
    row = add_memory(db, '用户在上海读研', kind='profile', keywords='上海 读研')
    assert row.id >= 1 and row.source == 'ai' and row.source_conversation_id is None
    row.keywords = '上海 读研 导师'
    db.commit()
    assert db.get(AIMemory, row.id).keywords == '上海 读研 导师'
    db.delete(row)
    db.commit()
    assert db.get(AIMemory, row.id) is None


# ---- save_memory ----

def test_save_memory_creates_and_captures_conversation(db):
    from types import SimpleNamespace
    ctx = SimpleNamespace(deps=SimpleNamespace(conversation_id=42))
    out = save_memory(db, 'preference', '汇报要用简体中文', keywords='语言 偏好', ctx=ctx)
    import json
    data = json.loads(out)
    row = db.get(AIMemory, data['id'])
    assert row.source == 'ai' and row.source_conversation_id == 42 and row.kind == 'preference'


def test_save_memory_rejects_similar_duplicate_with_model_retry(db):
    add_memory(db, '用户偏好清晨跑步，每周四次')
    with pytest.raises(ModelRetry) as exc:
        save_memory(db, 'fact', '用户偏好清晨跑步，每周四次！')
    message = str(exc.value)
    assert '#1' in message and 'update_memory' in message  # 校验即教学：指路已有条目与改法


def test_save_memory_rejects_invalid_kind_and_long_content(db):
    with pytest.raises(ModelRetry):
        save_memory(db, 'diary', '今天天气不错')  # kind 不在枚举内
    with pytest.raises(ModelRetry):
        save_memory(db, 'fact', '长' * 301)  # 超过 300 字上限


def test_save_memory_enforces_total_cap(db):
    db.add_all([AIMemory(kind='fact', content=f'记忆条目{i}', source='ai') for i in range(200)])
    db.commit()
    assert memory_count(db) == 200
    with pytest.raises(ModelRetry) as exc:
        save_memory(db, 'fact', '全新的另一条事实')
    assert '200' in str(exc.value) and ('合并' in str(exc.value) or '清理' in str(exc.value))


# ---- update_memory / forget_memory ----

def test_update_memory_refreshes_content_keywords(db):
    row = add_memory(db, '项目代号是启明', keywords='启明')
    out = update_memory(db, row.id, '项目代号已改为晨光', keywords='晨光 项目')
    row = db.get(AIMemory, row.id)
    assert row.content == '项目代号已改为晨光' and row.keywords == '晨光 项目'
    import json
    assert json.loads(out)['ok'] is True


def test_update_memory_keeps_keywords_when_blank(db):
    row = add_memory(db, '用户用 Vim', keywords='编辑器')
    update_memory(db, row.id, '用户改用 Emacs 了')
    assert db.get(AIMemory, row.id).keywords == '编辑器'


def test_update_and_forget_missing_id_raise_model_retry(db):
    with pytest.raises(ModelRetry):
        update_memory(db, 999, '不存在')
    with pytest.raises(ModelRetry):
        forget_memory(db, 999)


def test_forget_memory_deletes_row(db):
    row = add_memory(db, '不再正确的旧事实')
    import json
    assert json.loads(forget_memory(db, row.id))['ok'] is True
    assert db.get(AIMemory, row.id) is None


# ---- search_memory ----

def test_search_memory_matches_keywords_and_content(db):
    add_memory(db, '导师要求每周五提交组会汇报', keywords='导师 组会', kind='project')
    add_memory(db, '用户偏好喝美式咖啡', keywords='咖啡 偏好', kind='preference')
    import json
    hits = json.loads(search_memory(db, '组会 导师'))['memories']
    assert len(hits) == 1 and '组会' in hits[0]['content']
    # content 也能命中
    hits = json.loads(search_memory(db, '美式'))['memories']
    assert len(hits) == 1 and hits[0]['kind'] == 'preference'
    assert json.loads(search_memory(db, '不存在的词'))['count'] == 0
    with pytest.raises(ModelRetry):
        search_memory(db, '  ')


# ---- registry 门控（默认开：DEFAULTS 兜底；显式 false 关闭） ----

def test_registry_gating_defaults_on_and_off(db):
    assert {'save_memory'} <= MEMORY_TOOLS  # 自我防呆：工具名单完整
    names = {s.name for s in specs_for(db)}
    assert MEMORY_TOOLS <= names  # 缺失视为开（settingsvc.DEFAULTS 兜底 'true'）
    assert memory_enabled(db) is True
    settingsvc.set_setting(db, 'feature_memory_enabled', 'false')
    names = {s.name for s in specs_for(db)}
    assert not MEMORY_TOOLS & names
    assert memory_enabled(db) is False


def test_memory_tools_never_in_core_tools():
    from zhishi.agent.tool_discovery import CORE_TOOLS
    assert not MEMORY_TOOLS & CORE_TOOLS  # 预算红线：不占小窗常驻工具位


# ---- 注入三档 ----

def _prefix_memory_section(prefix: str) -> str:
    start = prefix.find('【长期记忆】')
    return '' if start < 0 else prefix[start:prefix.index('\n\n【用户消息】')]


def test_injection_disabled_switch_injects_nothing(db):
    add_memory(db, '有记忆但开关关闭')
    settingsvc.set_setting(db, 'feature_memory_enabled', 'false')
    prefix = prompts.build_user_message_prefix(db)
    assert '【长期记忆】' not in prefix
    assert '【长期记忆】' not in prompts.build_instructions(db)


def test_injection_enabled_with_empty_library_injects_nothing(db):
    prefix = prompts.build_user_message_prefix(db)
    assert '【长期记忆】' not in prefix
    assert '【长期记忆】' not in prompts.build_instructions(db)  # 零记忆不加指引（预算安全）


def test_injection_with_memories_injects_and_truncates(db):
    from datetime import timedelta
    from datetime import datetime
    base = datetime(2026, 9, 1, 8, 0, 0)
    # 35 条 × ~35 字 > 注入上限，必触发截断
    for i in range(35):
        db.add(AIMemory(kind='fact', content=f'第{i}条记忆：这项长期事实需要被记住',
                        source='ai', updated_at=base + timedelta(minutes=i)))
    db.commit()
    prefix = prompts.build_user_message_prefix(db)
    section = _prefix_memory_section(prefix)
    assert section.startswith('【长期记忆】')
    assert '第34条记忆' in section  # 最新一条必在
    assert '第0条记忆' not in section  # 最旧一条被截掉
    assert MEMORY_MORE_NOTE in section  # 截断时注明可 search_memory 检索
    assert len(section) <= MEMORY_PREFIX_CHARS + len(MEMORY_MORE_NOTE) + 8
    assert '【长期记忆】' in prompts.build_instructions(db)  # 有记忆且开启 → 加使用指引
