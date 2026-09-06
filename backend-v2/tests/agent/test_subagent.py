"""Task 子代理：主代理经 task 工具派出只读子代理；
subagent_started/delta/completed 三事件穿透到主流；用量并入主 run。"""
import json
from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from zhishi.agent.runtime import AgentRuntime


def test_subagent_toolset_is_readonly_only(db):
    """子代理工具集 = 只读工具真子集：写类/confirm/递归 task 一律不进。"""
    from zhishi.agent.tools.macro import subagent_specs
    from zhishi.agent.tools.registry import specs_for
    names = {s.name for s in subagent_specs(db)}
    readonly = {s.name for s in specs_for(db) if s.safety == "readonly"}
    assert names <= readonly
    assert "import_timetable" not in names      # confirm 类写工具不进
    assert "task" not in names                  # 递归派生子代理不进
    assert "list_tasks" in names                # 只读工具可用


async def test_subagent_events_and_usage_merge(db):
    """task 工具派生只读子代理，事件穿透主流，用量并入主 run。"""
    async def sub_stream(messages, info):
        yield "调研结论：下周三有空"

    step = {"n": 0}

    async def main_stream(messages, info):
        step["n"] += 1
        if step["n"] == 1:
            yield {0: DeltaToolCall(
                name="task",
                json_args=json.dumps({"description": "查空闲", "instructions": "只调研"},
                                     ensure_ascii=False),
                tool_call_id="t1")}
        else:
            yield "调研已完成"

    rt = AgentRuntime(model=FunctionModel(stream_function=main_stream), db=db,
                      sub_model_factory=lambda: FunctionModel(stream_function=sub_stream))
    events = [e async for e in rt.run_stream(user_text="帮我调研", conversation_id=None)]
    types = [e["type"] for e in events]
    assert "subagent_started" in types and "subagent_delta" in types \
        and "subagent_completed" in types
    done = next(e for e in events if e["type"] == "subagent_completed")
    assert done["ok"] is True and "调研结论" in done["summary"]
    # 子代理事件位于 task 工具调用之后（同一主流内穿透）
    task_idx = types.index("tool_call_started")
    assert types.index("subagent_started") > task_idx


async def test_concurrent_runs_no_emit_cross_talk(tmp_path):
    """两个并发 run 各自派出 task 子代理：emit 通道经 per-run deps 注入，
    子代理事件各回各的主流（macro.bind 模块级全局的串线缺陷回归锁定）。
    各 run 用独立 session（对齐生产 per-request 语义，避免同 session 跨线程并发）。"""
    import asyncio
    import json
    from pydantic_ai.models.function import DeltaToolCall, FunctionModel
    from zhishi.agent.runtime import AgentRuntime
    from zhishi.infra.database import create_all, make_engine, make_session_factory

    engine = make_engine(tmp_path / "concurrent.db")
    create_all(engine)
    factory = make_session_factory(engine)

    def make(tag: str):
        step = {"n": 0}

        async def main_stream(messages, info):
            step["n"] += 1
            if step["n"] == 1:
                yield {0: DeltaToolCall(
                    name="task",
                    json_args=json.dumps({"description": f"{tag}调研"}, ensure_ascii=False),
                    tool_call_id=f"t-{tag}")}
            else:
                yield f"{tag}完成"

        async def sub_stream(messages, info):
            yield f"{tag}子代理结论"

        return AgentRuntime(model=FunctionModel(stream_function=main_stream),
                            db=factory(),
                            sub_model_factory=lambda: FunctionModel(stream_function=sub_stream))

    async def collect(rt):
        events = [e async for e in rt.run_stream(user_text="派子代理")]
        rt.db.close()
        return events

    try:
        events_a, events_b = await asyncio.gather(collect(make("A")), collect(make("B")))
    finally:
        engine.dispose()
    deltas_a = [e["delta"] for e in events_a if e["type"] == "subagent_delta"]
    deltas_b = [e["delta"] for e in events_b if e["type"] == "subagent_delta"]
    assert deltas_a == ["A子代理结论"]
    assert deltas_b == ["B子代理结论"]
    # 各自的 started/completed 也成对且描述不串
    assert [e["description"] for e in events_a if e["type"] == "subagent_started"] == ["A调研"]
    assert [e["description"] for e in events_b if e["type"] == "subagent_started"] == ["B调研"]
