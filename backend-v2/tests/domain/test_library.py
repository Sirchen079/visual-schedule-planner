import io
from zhishi.domain.library import service as ls
from zhishi.domain.tasks import service as ts
from zhishi.domain.tasks.schemas import TaskCreate


class _Upload:
    def __init__(self, name, data, content_type):
        self.filename = name
        self.file = io.BytesIO(data)
        self.content_type = content_type


def test_save_upload_and_attach(db, tmp_path):
    up = _Upload("课表.docx", b"PK\x03\x04fake", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    f = ls.save_upload(db, storage_root=tmp_path / "files", upload=up, notes="我的课表")
    assert f.original_name == "课表.docx" and f.parse_status == "pending"
    t = ts.create_task(db, TaskCreate(title="整理课表"))
    ls.attach_to_task(db, t.id, f.id)
    assert [x.original_name for x in ls.list_task_files(db, t.id)] == ["课表.docx"]
    ls.detach_from_task(db, t.id, f.id)
    assert ls.list_task_files(db, t.id) == []


def test_save_link_resource(db):
    f = ls.save_link(db, title="webpack 文档", url="https://webpack.js.org/", resource_type="link")
    assert f.resource_type == "link" and f.source_url.startswith("https://")


def test_trash_and_purge(db, tmp_path):
    up = _Upload("a.txt", b"hello", "text/plain")
    f = ls.save_upload(db, storage_root=tmp_path / "files", upload=up)
    ls.soft_delete(db, f.id)
    assert ls.list_files(db) == [] and len(ls.list_trash(db)) == 1
    ls.restore(db, f.id)
    ls.soft_delete(db, f.id)
    ls.purge(db, f.id)
    assert ls.list_trash(db) == []


def test_purge_file_detaches_from_tasks(db, tmp_path):
    """purge 文件先清 task_file 关联（FK 开启下曾被关联行阻断）。"""
    from zhishi.domain.models import task_file
    up = _Upload("a.txt", b"hello", "text/plain")
    f = ls.save_upload(db, storage_root=tmp_path / "files", upload=up)
    t = ts.create_task(db, TaskCreate(title="带附件任务"))
    ls.attach_to_task(db, t.id, f.id)
    ls.soft_delete(db, f.id)
    ls.purge(db, f.id)   # 修复前：IntegrityError（FK）
    assert ls.list_task_files(db, t.id) == []
    assert db.execute(task_file.select()).all() == []
