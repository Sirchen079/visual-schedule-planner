"""注入纪律：零附加零注入；有附加注入单块（label/路径/工具名齐全）；开关关闭零注入。"""
import pytest

from zhishi.agent.tools.folder_tools import FOLDER_FLAG, folder_context_block
from zhishi.domain import settingsvc
from zhishi.domain.models import AIConversationFolder
from zhishi.infra.database import make_engine, make_session_factory, create_all

# 规格原文头两行（逐字，含 ASCII 引号）
HEADER = ('【对话文件夹】用户为本对话附加了以下本地文件夹。用户说"这个项目/我们的代码"时指这些。\n'
          "需要时用 list_folder_files 列文件、read_folder_file 读文件、search_folder_files 搜索。")


@pytest.fixture
def db(tmp_path):
    engine = make_engine(tmp_path / "test.db")
    create_all(engine)
    session = make_session_factory(engine)()
    yield session
    session.close()
    engine.dispose()


def test_block_empty_when_no_folders(db):
    assert folder_context_block(db, conversation_id=7) == ""


def test_block_lists_folders_with_tool_names(db):
    # 附加两行（conversation_id=7）→ 块内含 "【对话文件夹】"、"list_folder_files"、"read_folder_file"、
    # "search_folder_files"、两个 label 与两个 root_path；
    # 另一会话（conversation_id=8）的附加不得出现
    db.add_all([AIConversationFolder(conversation_id=7, root_path="E:/repo-a", label="repo-a"),
                AIConversationFolder(conversation_id=7, root_path="E:/repo-b", label="repo-b"),
                AIConversationFolder(conversation_id=8, root_path="E:/other", label="other")])
    db.commit()
    block = folder_context_block(db, conversation_id=7)
    assert "【对话文件夹】" in block
    assert block.startswith(HEADER + "\n")
    for name in ("list_folder_files", "read_folder_file", "search_folder_files"):
        assert name in block
    assert "- repo-a → E:/repo-a" in block
    assert "- repo-b → E:/repo-b" in block
    assert "other" not in block and "E:/other" not in block
    # 单块：除头两行外只有每个 folder 一行，无多余内容
    assert block.count("\n") == 3


def test_block_empty_when_no_conversation(db):
    assert folder_context_block(db, conversation_id=None) == ""


def test_block_empty_when_flag_off(db):
    """kill switch：功能开关关闭时有附加行也零注入（与工具注册门控对称）。"""
    db.add(AIConversationFolder(conversation_id=7, root_path="E:/repo-a", label="repo-a"))
    db.commit()
    settingsvc.set_setting(db, FOLDER_FLAG, "false")
    assert folder_context_block(db, conversation_id=7) == ""
