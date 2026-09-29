"""对话文件夹附加 REST：CRUD/校验/级联清 chunk。"""
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from zhishi.server.app import create_app


def _mk_conversation(c) -> int:
    """直接经 session_factory 插一条会话，返回 id。"""
    from zhishi.domain.models import AIConversation
    with c.app.state.session_factory() as db:
        row = AIConversation(title="测试会话")
        db.add(row)
        db.commit()
        return row.id


def test_folders_crud(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        cid = _mk_conversation(c)
        base = f"/ai/conversations/{cid}/folders"

        # GET 空列表 []
        assert c.get(base).json() == []

        # POST 真实临时目录 → 201 返回 label=目录名
        folder = tmp_path / "我的项目"
        folder.mkdir()
        r = c.post(base, json={"root_path": str(folder)})
        assert r.status_code == 201
        row = r.json()
        assert row["label"] == "我的项目" and row["root_path"] == str(folder)

        # 重复 POST 同 root_path → 409
        assert c.post(base, json={"root_path": str(folder)}).status_code == 409

        # POST 不存在路径 → 400
        assert c.post(base, json={"root_path": str(tmp_path / "不存在")}).status_code == 400

        # POST 文件路径(非目录) → 400
        f = tmp_path / "a.txt"
        f.write_text("x", encoding="utf-8")
        assert c.post(base, json={"root_path": str(f)}).status_code == 400

        # GET 列表含该行
        rows = c.get(base).json()
        assert len(rows) == 1 and rows[0]["id"] == row["id"]

        # DELETE → 204 且再 GET 为空
        assert c.delete(f"{base}/{row['id']}").status_code == 204
        assert c.get(base).json() == []

        # DELETE 不存在 id → 404
        assert c.delete(f"{base}/{row['id']}").status_code == 404


def test_delete_purges_chunks(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        from zhishi.domain.models import FolderFileChunk
        cid = _mk_conversation(c)
        folder = tmp_path / "proj"
        folder.mkdir()
        fid = c.post(f"/ai/conversations/{cid}/folders",
                     json={"root_path": str(folder)}).json()["id"]
        # 手工插入 chunk 行（索引已建的场景）
        with c.app.state.session_factory() as db:
            db.add(FolderFileChunk(folder_id=fid, rel_path="a.txt", mtime=1.0, size=1,
                                   line_start=1, line_end=1, content="x"))
            db.commit()
            assert db.scalars(
                select(FolderFileChunk).where(FolderFileChunk.folder_id == fid)).all()
        # DELETE 后 chunk 表无该 folder_id 的行（显式清，不依赖 FK 级联）
        assert c.delete(f"/ai/conversations/{cid}/folders/{fid}").status_code == 204
        with c.app.state.session_factory() as db:
            assert db.scalars(
                select(FolderFileChunk).where(FolderFileChunk.folder_id == fid)).all() == []


def test_unknown_conversation_404(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        folder = tmp_path / "p"
        folder.mkdir()
        assert c.get("/ai/conversations/999/folders").status_code == 404
        assert c.post("/ai/conversations/999/folders",
                      json={"root_path": str(folder)}).status_code == 404
        assert c.delete("/ai/conversations/999/folders/1").status_code == 404
