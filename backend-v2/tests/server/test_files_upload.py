# tests/server/test_files_upload.py
"""re #B6：POST /api/files 的 notes 从 query 参数改为 multipart 表单域。
表单传法此前被静默忽略；openapi requestBody 如实标注 multipart + notes 字段。"""
from fastapi.testclient import TestClient
from zhishi.server.app import create_app


def test_upload_notes_via_form_field(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        r = c.post("/api/files",
                   files={"file": ("a.txt", b"hello", "text/plain")},
                   data={"notes": "章节摘要"})
        assert r.status_code == 201
        assert r.json()["notes"] == "章节摘要"     # 此前为空字符串（被忽略）


def test_upload_without_notes_still_works(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        r = c.post("/api/files", files={"file": ("b.txt", b"x", "text/plain")})
        assert r.status_code == 201 and r.json()["notes"] == ""


def test_upload_openapi_declares_notes_as_form_field(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        spec = c.app.openapi()
        op = spec["paths"]["/api/files"]["post"]
        content = op["requestBody"]["content"]
        assert "multipart/form-data" in content
        schema = content["multipart/form-data"]["schema"]
        if "$ref" in schema:   # FastAPI 把表单字段包成 Body_xxx 组件
            schema = spec["components"]["schemas"][schema["$ref"].split("/")[-1]]
        props = schema["properties"]
        assert "file" in props and "notes" in props
        # notes 不再是 query 参数
        params = [p["name"] for p in op.get("parameters", [])]
        assert "notes" not in params
