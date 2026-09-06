
import json
import typing
from pathlib import Path
from zhishi.agent import events as ev

EXPECTED = {
    "run_started", "stage_changed", "heartbeat", "text_delta", "reasoning_delta",
    "tool_call_started", "tool_call_args_delta", "tool_call_result",
    "tool_approval_requested", "tool_approval_resolved", "plan_card",
    "work_plan_updated", "subagent_started", "subagent_delta", "subagent_completed",
    "usage_updated", "run_completed", "run_error", "done",
}

def test_all_19_events_defined():
    names = {m.model_fields["type"].default for m in ev.ALL_EVENTS}
    assert names == EXPECTED

def test_every_event_has_version():
    for m in ev.ALL_EVENTS:
        samples = {}
        for k, f in m.model_fields.items():
            if f.is_required() and k not in ("type", "v"):
                origin = typing.get_origin(f.annotation)
                if origin is typing.Literal:
                    samples[k] = typing.get_args(f.annotation)[0]
                elif origin is list:
                    samples[k] = []
                elif origin is dict:
                    samples[k] = {}
                elif f.annotation is bool:
                    samples[k] = True
                elif f.annotation is int:
                    samples[k] = 1
                elif f.annotation is float:
                    samples[k] = 1.5
                else:
                    samples[k] = "x"
        assert m(v=1, **samples) is not None

def test_schema_export_matches_committed():
    schema = ev.schema_union()
    committed = Path("docs/contracts/events.schema.json")
    assert committed.exists()
    assert json.loads(committed.read_text(encoding="utf-8")) == schema
