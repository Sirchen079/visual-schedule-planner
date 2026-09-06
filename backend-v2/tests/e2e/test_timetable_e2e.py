"""课表导入端到端测试：上传合成 DOCX、提取条目、批量导入并核对 RRULE。

FunctionModel 固定模型输出，验证工具协议及调用次数。测试显式启用自主档，
使批量导入直接执行；生产审批行为另由权限和审批测试覆盖。"""
import io
import json
from fastapi.testclient import TestClient
from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from zhishi.server.app import create_app
from tests.server.test_ai_routes import parse_sse

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

# FunctionModel 无理解能力，条目由测试代行"模型提取"，与 docx 单元格内容一致
ENTRIES = [
    {"title": "示例课程A", "weekday": 2, "periods": [2, 3], "location": "示例教室A",
     "week_kind": "range", "start_week": 2, "end_week": 13},
    {"title": "双周实验", "weekday": 4, "periods": [3, 4], "location": "示例教室B",
     "week_kind": "even", "start_week": 6, "end_week": 12},
]


def _make_timetable_docx() -> bytes:
    from docx import Document
    doc = Document()
    t = doc.add_table(rows=4, cols=3)
    t.cell(0, 0).text = "节次"; t.cell(0, 1).text = "星期二"; t.cell(0, 2).text = "星期四"
    t.cell(1, 0).text = "2"
    t.cell(1, 1).text = "示例课程A[连续周2-13周]示例教师甲[示例教室A]"
    t.cell(2, 0).text = "3"
    t.cell(2, 2).text = "双周实验[双周6-12周]示例教师乙[示例教室B]"
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
        assert {"示例课程A", "双周实验"} <= titles
        shiyan = next(e for e in events_db if e.title == "双周实验")
        assert "INTERVAL=2" in (shiyan.recur_rrule or "")
        # 附件解析文本确已注入模型输入（read-before-write 前提）
        from zhishi.domain.models import AIMessage
        with c.app.state.session_factory() as db:
            user_msg = db.query(AIMessage).filter_by(role="user").first()
        assert "示例课程A" in user_msg.display_json
