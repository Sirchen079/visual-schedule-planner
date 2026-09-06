# tests/server/test_attachments.py
"""对话附件：POST /ai/attachments 上传即解析（缓存落库）；
聊天时 attachment_ids 把解析文本注入模型输入，excerpt 落 display_json。"""
import json
from fastapi.testclient import TestClient
from zhishi.server.app import create_app


def _parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


def test_upload_and_inject_text_attachment(tmp_path, monkeypatch):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        # 伪 docx：monkeypatch 解析器返回课表结构
        from zhishi.adapters import parsers
        monkeypatch.setattr(
            parsers, "parse_file",
            lambda p: parsers.ParsedDoc(
                kind="docx", tables=[[["节次", "星期一"], ["2", "高数[连续周1-16周]"]]]))
        r = c.post("/ai/attachments", files={"file": ("课表.docx", b"PK",
                   "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
        assert r.status_code == 201
        body = r.json()
        file_id = body["file_id"]
        assert body["kind"] == "docx" and body["parse_status"] == "parsed"

        # 发消息带附件：runtime 把解析文本注入用户消息（TestModel 驱动）
        import zhishi.server.routes.ai as ai_route
        from pydantic_ai.models.test import TestModel
        monkeypatch.setattr(ai_route, "build_model",
                            lambda cfg, api_key=None: TestModel(call_tools=[]))
        from zhishi.domain.models import AIConfig
        with c.app.state.session_factory() as db:
            db.add(AIConfig(name="t", provider_kind="openai_compat", model="t",
                            base_url="http://x", enabled=True)); db.commit()
        r2 = c.post("/ai/chat/stream", json={"message": "帮我看看课表",
                                             "attachment_ids": [file_id]})
        events = _parse_sse(r2.text)
        assert events[0]["type"] == "run_started"
        # 附件内容已进入模型输入：落库的 user 消息 display 含解析文本摘要（excerpt）
        from zhishi.domain.models import AIMessage
        with c.app.state.session_factory() as db:
            user_msg = db.query(AIMessage).filter_by(role="user").first()
        display = json.loads(user_msg.display_json)
        att = display["attachments"][0]
        assert att["id"] == file_id and att["name"] == "课表.docx"
        assert "高数" in att["excerpt"]


def test_upload_image_marks_needs_vision(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        r = c.post("/ai/attachments", files={"file": ("pic.png", b"\x89PNG", "image/png")})
        assert r.status_code == 201
        assert r.json()["parse_status"] == "needs_vision"


def _seed_enabled_config(c, modalities=None):
    from zhishi.domain.models import AIConfig
    with c.app.state.session_factory() as db:
        db.add(AIConfig(name="t", provider_kind="openai_compat", model="t",
                        base_url="http://x", enabled=True,
                        input_modalities_json=json.dumps(modalities or ['text', 'image'])))
        db.commit()


def test_image_attachment_injected_as_binary_content(tmp_path, monkeypatch):
    """图片附件（needs_vision）→ BinaryContent 注入模型输入消息序列（多模态视觉）。"""
    from pydantic_ai.messages import BinaryContent
    from pydantic_ai.models.function import FunctionModel
    with TestClient(create_app(data_dir=tmp_path)) as c:
        r = c.post("/ai/attachments", files={"file": ("pic.png", b"\x89PNG-fake-bytes", "image/png")})
        file_id = r.json()["file_id"]
        _seed_enabled_config(c)

        seen = {}

        async def stream(messages, info):
            seen["content"] = messages[-1].parts[-1].content   # 最后一条 UserPromptPart
            yield "收到图片"

        import zhishi.server.routes.ai as ai_route
        monkeypatch.setattr(ai_route, "build_model",
                            lambda cfg, api_key=None: FunctionModel(stream_function=stream))
        r2 = c.post("/ai/chat/stream", json={"message": "看这张图", "attachment_ids": [file_id]})
        events = _parse_sse(r2.text)
        errs = [e for e in events if e["type"] == "run_error"]
        assert not errs, errs
        content = seen["content"]
        assert isinstance(content, list)
        assert any(isinstance(x, BinaryContent) and x.media_type == "image/png"
                   and b"\x89PNG-fake-bytes" == bytes(x.data) for x in content)


def test_declared_vision_rejection_reports_configuration_error_without_retry(tmp_path, monkeypatch):
    """声明支持图片但接口拒绝时明确报错，不在内容未读取时伪装成功。"""
    from pydantic_ai.models.function import FunctionModel
    with TestClient(create_app(data_dir=tmp_path)) as c:
        r = c.post("/ai/attachments", files={"file": ("pic.png", b"\x89PNG", "image/png")})
        file_id = r.json()["file_id"]
        _seed_enabled_config(c)

        calls = {"n": 0}
        async def stream(messages, info):
            calls["n"] += 1
            raise RuntimeError("400 The model does not support image input (vision).")
            yield 'unreachable'

        import zhishi.server.routes.ai as ai_route
        monkeypatch.setattr(ai_route, "build_model",
                            lambda cfg, api_key=None: FunctionModel(stream_function=stream))
        r2 = c.post("/ai/chat/stream", json={"message": "看这张图", "attachment_ids": [file_id]})
        events = _parse_sse(r2.text)
        errs = [e for e in events if e["type"] == "run_error"]
        assert len(errs) == 1
        assert calls['n'] == 1
        assert '模型接口拒绝媒体输入' in errs[0]['message']


def test_text_model_receives_unread_notice_without_image_attempt(tmp_path, monkeypatch):
    from pydantic_ai.models.function import FunctionModel
    with TestClient(create_app(data_dir=tmp_path)) as c:
        fid = c.post('/ai/attachments', files={'file': ('pic.png', b'\x89PNG', 'image/png')}).json()['file_id']
        _seed_enabled_config(c, ['text'])
        seen = []
        async def stream(messages, info):
            seen.append(messages[-1].parts[-1].content)
            yield '请配置视觉服务后重试。'
        import zhishi.server.routes.ai as ai_route
        monkeypatch.setattr(ai_route, 'build_model', lambda cfg: FunctionModel(stream_function=stream))
        events = _parse_sse(c.post('/ai/chat/stream', json={'message': '看图', 'attachment_ids': [fid]}).text)
        assert not [e for e in events if e['type'] == 'run_error']
        assert len(seen) == 1 and isinstance(seen[0], str)
        assert '未启用视觉 MCP' in seen[0] and '附件内容未读取' in seen[0]


def test_audio_upload_is_media_not_failed_document(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        response = c.post('/ai/attachments', files={'file': ('clip.wav', b'RIFF', 'audio/wav')})
        assert response.status_code == 201
        assert response.json()['kind'] == 'audio'
        assert response.json()['parse_status'] == 'needs_media'
