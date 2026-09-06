"""批量工具注册表。ToolSpec 持有工具函数；模块导入时幂等注册。"""
from zhishi.agent.tools.registry import REGISTRY, ToolSpec, register
from zhishi.agent.tools import macro


_MACRO_SPECS = [
    ToolSpec("import_document", macro.import_document.__doc__ or "", "safe", None, macro.import_document),
    ToolSpec("import_timetable", macro.import_timetable.__doc__ or "", "confirm", None, macro.import_timetable),
    ToolSpec("plan_day", macro.plan_day.__doc__ or "", "readonly", None, macro.plan_day),
    ToolSpec("apply_day_plan", macro.apply_day_plan.__doc__ or "", "confirm", None, macro.apply_day_plan),
    ToolSpec("reschedule_overdue", macro.reschedule_overdue.__doc__ or "", "confirm", None, macro.reschedule_overdue),
    ToolSpec("task", macro.task.__doc__ or "", "safe", None, macro.task),   # 只派只读子代理
    ToolSpec("propose_plan", macro.propose_plan.__doc__ or "", "readonly", None, macro.propose_plan),
    # 其余 L2/L3 工具在任务 8 中逐个加入本表
]


def install() -> None:
    existing = {s.name for s in REGISTRY}
    for spec in _MACRO_SPECS:
        if spec.name not in existing:
            register(spec)


install()
