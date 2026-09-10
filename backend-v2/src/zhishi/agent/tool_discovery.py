"""Local tool discovery using ordinary function calls on every supported provider."""
from __future__ import annotations

import json
import re
from dataclasses import replace
from math import sqrt
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.messages import ToolCallPart, ToolReturnPart
from zhishi.agent.context_parts import append_context, latest_context

CORE_TOOLS = {'search_tools', 'execute_tool', 'ask_user', 'update_work_plan', 'read_tool_result'}
EXECUTE_DESCRIPTION = ('执行 search_tools 返回的工具。name 填准确工具名，arguments 按返回的 parameters 填写。'
                       '工作流和 next_call 中的工具也通过此入口调用；未获得参数定义时先查询。权限仍由系统检查。')
SEARCH_DESCRIPTION = (
    '按用途或准确名称查找并加载工具。query可用中文或英文，names可给已知工具名。'
    '一次返回最多6个工具的完整参数定义；使用 execute_tool(name, arguments) 执行。未找到时换关键词，不猜参数。'
    '任务/日程/提醒、账本/账单、收件箱、学习研究、资料阅读、联网、习惯、目标、日记、计时、MCP均可查询。'
)

# A tool mentioned as something to avoid does not activate that whole workflow.
SKILL_TOOLS = {
    '内置·长材料阅读': {'read_material', 'search_materials'},
    '内置·持续跟进': {'check_research_progress', 'get_secretary_followup', 'apply_secretary_followup',
                    'respond_secretary_followup', 'get_research_watch', 'configure_research_watch'},
    '内置·学习与研究项目': {'create_research_project', 'get_research_project', 'list_research_projects',
                        'research_project_sources', 'attach_research_material', 'add_research_source',
                        'preview_research_plan', 'apply_research_plan', 'update_research_project',
                        'preview_research_replan', 'record_research_feedback'},
    '内置·材料收件箱': {'propose_inbox_items', 'list_inbox_items', 'get_inbox_item', 'revise_inbox_item',
                      'apply_inbox_item', 'reject_inbox_item'},
    '内置·个人账本': {'record_transaction', 'list_transactions', 'get_transaction', 'summarize_transactions',
                    'update_transaction', 'delete_transaction', 'restore_transaction',
                    'create_bill', 'list_bills', 'get_bill', 'confirm_bill_payment', 'get_bill_history',
                    'update_bill', 'skip_bill_occurrence'},
    '内置·任务、提醒与日程': {'create_task', 'create_subtasks', 'update_task', 'create_event', 'update_event',
                          'assign_task_to_day', 'import_timetable', 'plan_day', 'apply_day_plan',
                          'reschedule_overdue', 'get_range_load', 'find_free_slots', 'check_conflicts'},
    '内置·跨域联动': {'check_in_habit', 'update_kr_progress', 'write_journal', 'start_timer', 'stop_timer', 'get_time_stats'},
}


def _terms(text: str) -> set[str]:
    value = text.casefold()
    terms = set(re.findall(r'[a-z0-9]+', value))
    for word in re.findall(r'[\u3400-\u9fff]+', value):
        terms.update(word[i:i + 2] for i in range(len(word) - 1))
        if len(word) == 1:
            terms.add(word)
    return terms


class ToolDiscovery:
    """Keep execution/permission registration intact while reducing wire schemas.

    Discovery runs locally, never emits native ``tool_search`` protocol fields,
    and only advertises tools present in this run's enabled/plan-mode toolset.
    Wire entry points stay fixed; full schemas travel in discovery results.
    A recent working set selects relevant skill context through ordinary history.
    """

    def __init__(self, skills: list[tuple[str, str]] = (), unavailable: dict | None = None,
                 plan_mode: bool = False):
        self.catalog: dict = {}
        self.skills = sorted(skills)
        self.unavailable = unavailable if unavailable is not None else {}
        self.core_tools = CORE_TOOLS | ({'propose_plan'} if plan_mode else set())

    def search(self, ctx: RunContext[Any], query: str = '', names: list[str] | None = None) -> str:
        """按中文用途、英文关键词或准确名称加载所需工具。"""
        requested = list(dict.fromkeys(names or []))[:6]
        available = {name: tool for name, tool in self.catalog.items() if name not in self.core_tools}
        selected = [name for name in requested if name in available]
        needle = query.strip().casefold()
        exact_name = next((name for name in available if name.casefold() == needle), None)
        if exact_name and not requested:
            selected = [exact_name]
        terms = _terms(needle)
        from zhishi.agent.tool_workflows import route_for
        route = route_for(needle, set(available)) if not requested and not exact_name else None
        if route:
            selected += list(dict.fromkeys(s['tool'] for s in route['steps']))[:6]
        scored = []
        for name, tool in available.items():
            if name in selected:
                continue
            description = tool.description or ''
            haystack = f'{name} {description}'
            overlap = len(terms & _terms(haystack))
            score = (100 if needle and needle in name.casefold() else 0)
            score += (20 if needle and needle in description.casefold() else 0)
            score += overlap / sqrt(max(1, len(_terms(haystack))))
            if score:
                scored.append((-score, name))
        if not route and not exact_name:
            selected += [name for _, name in sorted(scored)[:6 - len(selected)]]
        return json.dumps({'loaded_tools': selected,
            'tools': [{'name': name, 'description': available[name].description or '',
                       'parameters': available[name].parameters_json_schema}
                      for name in selected],
            'unknown_names': [name for name in requested if name not in available],
            **({'workflow':route} if route else {}),
            **({'unavailable_services':list(self.unavailable.values())} if self.unavailable else {}),
            'next_step': ('使用 execute_tool(name=工具名, arguments=按 parameters 填写的参数对象)；执行权限仍由系统检查。' if selected else
                          '没有匹配工具。换用更短关键词或准确工具名；工具未启用时说明缺口。')}, ensure_ascii=False)

    async def execute(self, ctx: RunContext[Any], name: str, arguments: dict[str, Any]) -> Any:
        """Dispatch through the registered SDK toolset, including its validation and permission gate."""
        from pydantic import ValidationError
        from pydantic_ai import ModelRetry
        from pydantic_ai.tools import ToolDenied
        # ctx.tool_manager is rebuilt on resume, before the first model request.
        if name in self.core_tools:
            raise ModelRetry('此工具是固定入口，请直接调用，不要经 execute_tool 嵌套调用。')
        if name not in ctx.tools:
            raise ModelRetry('工具不存在或本轮未启用，请重新 search_tools 查询可用工具。')
        try:
            result = await ctx.tool_manager.handle_call(
                ToolCallPart(name, arguments, tool_call_id=ctx.tool_call_id),
                approved=ctx.tool_call_approved, wrap_validation_errors=False)
        except ValidationError as exc:
            raise ModelRetry(str(exc)) from exc
        if isinstance(result, ToolDenied):
            return {'ok': False, 'denied': True}
        # The SDK counts both inner execution and this wrapper; only one business
        # call occurred. No await between adjustment and returning to the SDK.
        ctx.usage.tool_calls -= 1
        return result

    def _working_set(self, messages: list) -> set[str]:
        recent = []
        call_names = {}
        for message in messages:
            for part in message.parts:
                names = []
                if isinstance(part, ToolCallPart) and part.tool_name in self.catalog:
                    names = [actual_tool_call(part).tool_name]
                    call_names[part.tool_call_id] = names[0]
                elif isinstance(part, ToolReturnPart):
                    try:
                        value = json.loads(part.content) if isinstance(part.content, str) else part.content
                        found = value.get('loaded_tools', []) if isinstance(value, dict) and part.tool_name == 'search_tools' else []
                        source = call_names.get(part.tool_call_id, part.tool_name)
                        if isinstance(value, dict) and not source.startswith('mcp__'):
                            next_call = value.get('next_call')
                            if isinstance(next_call, dict) and isinstance(next_call.get('tool'), str):
                                found = [*found, next_call['tool']]
                        names = [name for name in found if isinstance(name, str) and name in self.catalog]
                    except (ValueError, TypeError):
                        pass
                for name in names:
                    if name in recent:
                        recent.remove(name)
                    recent.append(name)
        return set(recent[-18:]) | self.core_tools

    def hook(self):
        from pydantic_ai.capabilities import Hooks

        def prepare(ctx, request):
            parameters = request.model_request_parameters
            self.catalog = {tool.name: tool for tool in parameters.function_tools}
            active = self.core_tools
            visible = []
            for tool in parameters.function_tools:
                if tool.name not in active:
                    continue
                if tool.name == 'search_tools':
                    # Semantic discovery supplies names; avoid sending the entire
                    # directory on every request, including simple follow-ups.
                    tool = replace(tool, description=SEARCH_DESCRIPTION)
                visible.append(tool)
            return self._with_context(replace(request,
                model_request_parameters=replace(parameters, function_tools=visible)))

        return Hooks(before_model_request=prepare)

    def context_hook(self):
        from pydantic_ai.capabilities import Hooks
        return Hooks(before_model_request=lambda ctx, request: self._with_context(request))

    def _with_context(self, request):
        # Run again after compaction: newly required rules cannot disappear
        # between discovery and the actual model request.
        active = self._working_set(request.messages)
        messages = request.messages
        if self.unavailable:
            state = ('【本轮外部工具状态】' + json.dumps(
                [self.unavailable[key] for key in sorted(self.unavailable)], ensure_ascii=False, sort_keys=True) +
                '继续可用工具能完成的部分；不得声称已使用不可用服务。')
        else:
            state = '【本轮外部工具状态】当前未报告连接不可用；实际执行仍以工具结果为准。'
        previous = latest_context(messages, 'tool-status')
        if previous != state and (previous is not None or self.unavailable):
            messages = append_context(messages, 'tool-status', state)
        for title, content in self.skills:
            relevant = (bool(SKILL_TOOLS[title] & active) if title in SKILL_TOOLS else
                any(re.search(r'(?<![a-zA-Z0-9_])' + re.escape(name) + r'(?![a-zA-Z0-9_])', content)
                    for name in active - CORE_TOOLS))
            if relevant:
                text = f'【技能：{title}】\n{content}'
                if latest_context(messages, f'skill:{title}') != text:
                    messages = append_context(messages, f'skill:{title}', text)
        return replace(request, messages=messages)


def actual_tool_call(call):
    """Unwrap for previews/traces only; wire history keeps its original call name."""
    if call.tool_name == 'execute_tool':
        try:
            args = call.args_as_dict()
            if isinstance(args.get('name'), str) and isinstance(args.get('arguments'), dict):
                return replace(call, tool_name=args['name'], args=args['arguments'])
        except (ValueError, TypeError):
            pass
    return call
