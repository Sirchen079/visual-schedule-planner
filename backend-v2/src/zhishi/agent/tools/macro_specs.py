# src/zhishi/agent/tools/macro_specs.py
"""L2/L3 大颗粒工具注册表：与 atomic_read._READ_SPECS 同模式。
偏差（对计划）：ToolSpec 第 5 字段在实际 registry.py 中是 fn: Callable（非 fn_name 字符串），
故此处传 macro 模块的实际函数对象。
集成修复（任务 7 发现）：此前 install() 无人调用，macro 工具从未进注册表——
runtime 权限门会以"不在白名单"拒绝一切 L2/L3 工具。与 atomic_read/atomic_write
同模式：模块导入即注册（幂等，防重复）。"""
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
