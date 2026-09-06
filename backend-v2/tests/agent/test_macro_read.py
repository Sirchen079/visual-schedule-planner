# tests/agent/test_macro_read.py
import json
from zhishi.adapters.parsers import ParsedDoc


def _library_file(db, tmp_path, name="课表.docx", parsed=None):
    from zhishi.domain.library import service as ls
    (tmp_path / "files").mkdir(exist_ok=True)
    src = tmp_path / "files" / name
    src.write_bytes(b"PK")
    f = ls.save_local_file(db, storage_root=tmp_path / "files", source=src)
    return f


def test_ensure_parsed_caches(db, tmp_path, monkeypatch):
    from zhishi.domain.library import service as ls
    f = _library_file(db, tmp_path)
    monkeypatch.setattr("zhishi.adapters.parsers.parse_file",
                        lambda p: ParsedDoc(kind="docx", text="课表内容",
                                            tables=[[["节次", "星期一"], ["2", "高数"]]]))
    doc1 = ls.ensure_parsed(db, f, storage_root=tmp_path / "files")
    assert doc1.kind == "docx"
    db.refresh(f)
    assert f.parse_status == "parsed" and "课表内容" in f.extracted_text
    # 二次调用走缓存（不再触发解析：换一个会报错的 parse_file 证明未调用）
    def boom(p):
        raise AssertionError("不应重复解析")
    monkeypatch.setattr("zhishi.adapters.parsers.parse_file", boom)
    doc2 = ls.ensure_parsed(db, f, storage_root=tmp_path / "files")
    assert doc2.kind == "docx"


def test_import_document_tool(db, tmp_path, monkeypatch):
    from zhishi.agent.tools import macro
    f = _library_file(db, tmp_path)
    monkeypatch.setattr("zhishi.adapters.parsers.parse_file",
                        lambda p: ParsedDoc(kind="docx", tables=[[["节次", "星期一"], ["2", "高数[连续周1-16周]"]]]))
    from zhishi.domain.library import service as ls
    ls.ensure_parsed(db, f, storage_root=tmp_path / "files")
    out = json.loads(macro.import_document(db, file_id=f.id))
    assert out["kind"] == "docx"
    assert out["tables"][0][1][1].startswith("高数")
