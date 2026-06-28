import json
from io import BytesIO

import pytest

from app.services import ai_client


def test_openai_chat_request_includes_image_and_document_blocks():
    req = ai_client.build_provider_request(
        provider="openai_chat",
        model="vision-model",
        api_key="key",
        messages=[
            {
                "role": "user",
                "content": "请分析附件",
                "attachments": [
                    {
                        "kind": "document",
                        "filename": "paper.txt",
                        "mime_type": "text/plain",
                        "text": "论文摘要：研究日程规划。",
                    },
                    {
                        "kind": "image",
                        "filename": "chart.png",
                        "mime_type": "image/png",
                        "data": "YWJj",
                    },
                ],
            }
        ],
        system_prompt="system",
        extra_headers={},
        base_url="https://api.example.com",
        full_url=None,
        proxy_url=None,
    )

    content = req.json["messages"][1]["content"]
    assert content[0] == {"type": "text", "text": "请分析附件"}
    assert "paper.txt" in content[1]["text"]
    assert "论文摘要" in content[1]["text"]
    assert "chart.png" in content[2]["text"]
    assert content[3]["type"] == "image_url"
    assert content[3]["image_url"]["url"] == "data:image/png;base64,YWJj"


def test_openai_responses_request_uses_input_image_blocks():
    req = ai_client.build_provider_request(
        provider="openai_responses",
        model="vision-model",
        api_key="key",
        messages=[
            {
                "role": "user",
                "content": "看图",
                "attachments": [
                    {
                        "kind": "image",
                        "filename": "chart.jpg",
                        "mime_type": "image/jpeg",
                        "data": "YWJj",
                    }
                ],
            }
        ],
        system_prompt="system",
        extra_headers={},
        base_url="https://api.example.com",
        full_url=None,
        proxy_url=None,
    )

    content = req.json["input"][1]["content"]
    assert content == [
        {"type": "input_text", "text": "看图"},
        {"type": "input_text", "text": "图片附件: chart.jpg\n附件 ID: None\n类型: image/jpeg\n大小: 0 bytes"},
        {"type": "input_image", "image_url": "data:image/jpeg;base64,YWJj"},
    ]


def test_claude_request_uses_base64_image_source():
    req = ai_client.build_provider_request(
        provider="claude_messages",
        model="claude-test",
        api_key="key",
        messages=[
            {
                "role": "user",
                "content": "看图",
                "attachments": [
                    {
                        "kind": "image",
                        "filename": "chart.webp",
                        "mime_type": "image/webp",
                        "data": "YWJj",
                    }
                ],
            }
        ],
        system_prompt="system",
        extra_headers={},
        base_url="https://api.example.com",
        full_url=None,
        proxy_url=None,
    )

    image = req.json["messages"][0]["content"][2]
    assert image == {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/webp",
            "data": "YWJj",
        },
    }


@pytest.mark.anyio
async def test_ai_chat_sends_uploaded_text_attachment_to_model(client, monkeypatch):
    config = client.post(
        "/ai/configs",
        json={
            "name": "test",
            "provider": "openai_chat",
            "model": "fake-model",
            "api_key": "test-key",
        },
    ).json()
    client.post(f"/ai/configs/{config['id']}/enable")
    uploaded = client.post(
        "/ai/attachments",
        files={"file": ("paper.txt", BytesIO("论文结论：需要三天阅读计划".encode("utf-8")), "text/plain")},
    )
    assert uploaded.status_code == 201

    captured = {}

    async def fake_call_provider(request):
        captured["payload"] = request.json
        return {"choices": [{"message": {"content": '{"reply":"已阅读","tools":[],"dangerous_actions":[]}'}}]}

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)
    resp = client.post(
        "/ai/chat",
        json={"message": "帮我规划", "attachments": [{"id": uploaded.json()["id"]}]},
    )

    assert resp.status_code == 200
    content = captured["payload"]["messages"][-1]["content"]
    assert any("paper.txt" in block.get("text", "") for block in content)
    assert any("三天阅读计划" in block.get("text", "") for block in content)


def test_extracts_docx_text(tmp_path):
    docx = pytest.importorskip("docx")
    from app.services import ai_attachment_service

    document = docx.Document()
    document.add_paragraph("论文标题：多模态日程规划")
    path = tmp_path / "paper.docx"
    document.save(path)

    text = ai_attachment_service.extract_document_text(
        path,
        "paper.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    assert "多模态日程规划" in text


def test_extracts_xlsx_text(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    from app.services import ai_attachment_service

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "阅读计划"
    sheet.append(["论文", "截止时间"])
    sheet.append(["多模态日程规划", "周六"])
    path = tmp_path / "paper.xlsx"
    workbook.save(path)

    text = ai_attachment_service.extract_document_text(
        path,
        "paper.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    assert "阅读计划" in text
    assert "多模态日程规划" in text


def test_extracts_pptx_text(tmp_path):
    pptx = pytest.importorskip("pptx")
    from app.services import ai_attachment_service

    presentation = pptx.Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[5])
    slide.shapes.title.text = "论文汇报计划"
    path = tmp_path / "paper.pptx"
    presentation.save(path)

    text = ai_attachment_service.extract_document_text(
        path,
        "paper.pptx",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )

    assert "论文汇报计划" in text


def test_corrupted_document_attachment_does_not_crash(tmp_path, monkeypatch):
    from app.services import ai_attachment_service

    database_dir = tmp_path / "data"
    database_dir.mkdir()
    monkeypatch.setattr(ai_attachment_service.settings, "ai_attachments_dir", tmp_path)
    monkeypatch.setattr(ai_attachment_service.settings, "database_dir", database_dir)
    path = tmp_path / "bad.pdf"
    path.write_bytes(b"not a real pdf")
    attachment = ai_attachment_service.ChatAttachment(
        id="badpdf123",
        original_name="bad.pdf",
        storage_path=str(path.relative_to(database_dir.parent)),
        size=path.stat().st_size,
        mime_type="application/pdf",
        kind="document",
        created_at=0,
    )
    (tmp_path / "badpdf123.json").write_text(json.dumps(attachment.__dict__), encoding="utf-8")

    items = ai_attachment_service.build_model_attachments(["badpdf123"])

    assert "解析失败" in items[0]["text"]
