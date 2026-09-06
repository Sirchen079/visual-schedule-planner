# tests/e2e/test_timetable_e2e.py
"""核心验收：课表导入全链 ≤4 次工具调用。
路径：上传 docx（真实解析）→ import_document（读表）→ 模型提取条目 →
import_timetable（批量建+冲突报告）→ RRULE 落库。
真实模型成功率验收（≥95%）属 CI 外手动项，本测试锁定协议与调用数上限。
偏差（对计划）：FunctionModel 无 ctx.tool_function_from_json API——按 pydantic-ai 2.38
stream_function 脚本化（计划自检条款允许）；agent_autonomy=autonomous 使 confirm 级
import_timetable 在 E2E 中直接执行（等价于用户授予自主档，不破坏生产审批语义）。"""
import io
import json
from fastapi.testclient import TestClient
from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from zhishi.server.app import create_app
from tests.server.test_ai_routes import parse_sse

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

# FunctionModel 无理解能力，条目由测试代行"模型提取"，与 docx 单元格内容一致
ENTRIES = [
    {"title": "数值分析", "weekday": 2, "periods": [2, 3], "location": "五教201",
     "week_kind": "range", "start_week": 2, "end_week": 13},
    {"title": "双周实验", "weekday": 4, "periods": [3, 4], "location": "东教503",
     "week_kind": "even", "start_week": 6, "end_week": 12},
]


def _make_timetable_docx() -> bytes:
    from docx import Document
    doc = Document()
    t = doc.add_table(rows=4, cols=3)
    t.cell(0, 0).text = "节次"; t.cell(0, 1).text = "星期二"; t.cell(0, 2).text = "星期四"
    t.cell(1, 0).text = "2"
    t.cell(1, 1).text = "数值分析5班[连续周2-13周]卢欣[五教201]"
    t.cell(2, 0).text = "3"
    t.cell(2, 2).text = "双周实验[双周6-12周]王强[东教503]"
    buf = io.BytesIO(); doc.save(buf)
    return buf.getvalue()


def _seed(db):
    from zhishi.domain import settingsvc
    from zhishi.domain.models import AIConfig
    settingsvc.set_setting(db, "agent_autonomy", "autonomous")
    db.add(AIConfig(name="t", provider_kind="openai_compat", model="t",
                    base_url="http://x", enabled=True))
    db.commit()


def test_timetable_e2e_within_4_tool_calls(tmp_path, monkeypatch):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        up = c.post("/ai/attachments",
                    files={"file": ("课表.docx", _make_timetable_docx(), DOCX_MIME)})
        assert up.status_code == 201
        body = up.json()
        file_id = body["file_id"]
        assert body["parse_status"] == "parsed"      # 真实 docx 解析管道可用
        _seed(c.app.state.session_factory())

        step = {"n": 0}

        async def scripted(messages, info):
            step["n"] += 1
            if step["n"] == 1:            # ① import_document：读课表表格
                yield {0: DeltaToolCall(name="import_document",
                                        json_args=json.dumps({"file_id": file_id}),
                                        tool_call_id="t1")}
            elif step["n"] == 2:          # ② import_timetable：批量建+冲突报告
                yield {0: DeltaToolCall(name="import_timetable",
                                        json_args=json.dumps(
                                            {"semester_start": "2026-09-07",
                                             "entries": ENTRIES}, ensure_ascii=False),
                                        tool_call_id="t2")}
            else:
                yield "已导入 2 门课，双周实验按双周 RRULE 重复。"

        import zhishi.server.routes.ai as ai_route
        monkeypatch.setattr(ai_route, "build_model",
                            lambda cfg, api_key=None: FunctionModel(stream_function=scripted))

        r = c.post("/ai/chat/stream",
                   json={"message": "把我的课表导入日程", "attachment_ids": [file_id]})
        assert r.status_code == 200
        events = parse_sse(r.text)
        types = [e["type"] for e in events]
        assert types[0] == "run_started" and types[-1] == "done"
        tool_calls = [e for e in events if e["type"] == "tool_call_started"]
        assert len(tool_calls) <= 4, f"超出调用预算: {len(tool_calls)}"
        assert {e["tool"] for e in tool_calls} == {"import_document", "import_timetable"}

        # 两门课建成，双周课正确落 INTERVAL=2 RRULE
        from zhishi.domain.models import Event
        with c.app.state.session_factory() as db:
            events_db = db.query(Event).all()
        titles = {e.title for e in events_db}
        assert {"数值分析", "双周实验"} <= titles
        shiyan = next(e for e in events_db if e.title == "双周实验")
        assert "INTERVAL=2" in (shiyan.recur_rrule or "")
        # 附件解析文本确已注入模型输入（read-before-write 前提）
        from zhishi.domain.models import AIMessage
        with c.app.state.session_factory() as db:
            user_msg = db.query(AIMessage).filter_by(role="user").first()
        assert "数值分析" in user_msg.display_json
