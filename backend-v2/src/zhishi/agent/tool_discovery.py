"""Local tool discovery using ordinary function calls on every supported provider."""
from __future__ import annotations

import json
import re
from dataclasses import replace
from math import sqrt
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.messages import InstructionPart, ToolCallPart, ToolReturnPart

CORE_TOOLS = {'search_tools', 'ask_user', 'read_tool_result', 'read_conversation_history',
              'propose_plan', 'update_work_plan'}
SEARCH_DESCRIPTION = (
    '按用途或准确名称查找并加载工具。query可用中文或英文，names可给已知工具名。'
    '一次加载最多6个；下一次请求即可调用。未找到时换关键词，不猜参数。'
    '任务/日程/提醒、账本/账单、收件箱、学习研究、资料阅读、联网、习惯、目标、日记、计时、MCP均可查询。'
)


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
    A bounded recent working set survives resume through ordinary tool history.
    """

    def __init__(self, skills: list[tuple[str, str]] = ()):
        self.catalog: dict = {}
        self.skills = list(skills)

    def search(self, ctx: RunContext[Any], query: str = '', names: list[str] | None = None) -> str:
        """按中文用途、英文关键词或准确名称加载所需工具。"""
        requested = list(dict.fromkeys(names or []))[:6]
        available = {name: tool for name, tool in self.catalog.items() if name not in CORE_TOOLS}
        selected = [name for name in requested if name in available]
        needle = query.strip().casefold()
        terms = _terms(needle)
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
        selected += [name for _, name in sorted(scored)[:6 - len(selected)]]
        return json.dumps({'loaded_tools': selected,
            'tools': [{'name': name, 'description': (available[name].description or '')[:220]}
                      for name in selected],
            'unknown_names': [name for name in requested if name not in available],
            'next_step': ('现在使用对应工具定义中的参数调用；执行权限仍由系统检查。' if selected else
                          '没有匹配工具。换用更短关键词或准确工具名；工具未启用时说明缺口。')}, ensure_ascii=False)

    def _working_set(self, messages: list) -> set[str]:
        recent = []
        for message in messages:
            for part in message.parts:
                names = []
                if isinstance(part, ToolCallPart) and part.tool_name in self.catalog:
                    names = [part.tool_name]
                elif isinstance(part, ToolReturnPart) and part.tool_name == 'search_tools':
                    try:
                        value = json.loads(part.content) if isinstance(part.content, str) else part.content
                        found = value.get('loaded_tools', []) if isinstance(value, dict) else []
                        names = [name for name in found if isinstance(name, str) and name in self.catalog]
                    except (ValueError, TypeError):
                        pass
                for name in names:
                    if name in recent:
                        recent.remove(name)
                    recent.append(name)
        return set(recent[-18:]) | CORE_TOOLS

    def hook(self):
        from pydantic_ai.capabilities import Hooks

        def prepare(ctx, request):
            parameters = request.model_request_parameters
            self.catalog = {tool.name: tool for tool in parameters.function_tools}
            active = self._working_set(request.messages)
            visible = []
            for tool in parameters.function_tools:
                if tool.name not in active:
                    continue
                if tool.name == 'search_tools':
                    # Names make precise discovery possible without sending schemas.
                    catalog = ', '.join(sorted(name for name in self.catalog if name not in CORE_TOOLS)[:180])
                    tool = replace(tool, description=f'{SEARCH_DESCRIPTION}\n工具目录：{catalog}')
                visible.append(tool)
            instructions = list(parameters.instruction_parts or [])
            for title, content in self.skills:
                if any(re.search(r'(?<![a-zA-Z0-9_])' + re.escape(name) + r'(?![a-zA-Z0-9_])', content)
                       for name in active - CORE_TOOLS):
                    instructions.append(InstructionPart(content=f'【技能：{title}】\n{content}'))
            return replace(request, model_request_parameters=replace(parameters,
                function_tools=visible, instruction_parts=instructions if instructions else parameters.instruction_parts))

        return Hooks(before_model_request=prepare)
