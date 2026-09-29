"""对话文件夹工具：list_folders 语义、registry 开关门控、CORE_TOOLS 守卫。"""
import pytest

from zhishi.agent.tools.folder_tools import FOLDER_FLAG, FOLDER_TOOLS, list_folders
from zhishi.agent.tools.registry import specs_for
from zhishi.agent.tool_discovery import CORE_TOOLS
from zhishi.domain import settingsvc
from zhishi.domain.models import AIConversation, AIConversationFolder
from zhishi.infra.database import make_engine, make_session_factory, create_all


@pytest.fixture
def db(tmp_path):
    engine = make_engine(tmp_path / "test.db")
    create_all(engine)
    session = make_session_factory(engine)()
    yield session
    session.close()
    engine.dispose()


def _conv(db) -> AIConversation:
    row = AIConversation(title="t"); db.add(row); db.commit(); db.refresh(row); return row


def test_list_folders_empty_teaches_attach(db):
    ctx = type("C", (), {"deps": type("D", (), {"conversation_id": 1})})()
    out = list_folders(db, ctx=ctx)   # type: ignore[arg-type]
    assert '"ok": false' in out and "附加" in out


def test_list_folders_lists_current_conversation_only(db):
    c1, c2 = _conv(db), _conv(db)
    db.add_all([AIConversationFolder(conversation_id=c1.id, root_path="E:/repo-a", label="repo-a"),
                AIConversationFolder(conversation_id=c2.id, root_path="E:/repo-b", label="repo-b")])
    db.commit()
    ctx = type("C", (), {"deps": type("D", (), {"conversation_id": c1.id})})()
    out = list_folders(db, ctx=ctx)   # type: ignore[arg-type]
    assert "repo-a" in out and "repo-b" not in out


def test_no_ctx_returns_error(db):
    assert '"ok": false' in list_folders(db)


def test_guard_not_in_core_tools_and_flag_gating(db):
    assert not FOLDER_TOOLS & CORE_TOOLS        # FOLDER_TOOLS 为最终四个名字的集合（本任务只注册 list_folders）
    names = {s.name for s in specs_for(db)}
    assert "list_folders" in names              # 默认开
    settingsvc.set_setting(db, FOLDER_FLAG, "false")
    assert "list_folders" not in {s.name for s in specs_for(db)}    # 关闭即下线
