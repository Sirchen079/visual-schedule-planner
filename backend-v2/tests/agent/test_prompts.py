# tests/agent/test_prompts.py
from zhishi.agent import prompts


def test_instructions_contains_core_sections(db):
    text = prompts.build_instructions(db)
    for section in ("幕僚", "工具使用规则", "read-before-write", "技能"):
        assert section in text


def test_plan_mode_instruction_only_in_plan_mode(db):
    """re #017 k3③：计划模式专用指令段仅在 plan_mode=True 时注入。"""
    assert "【计划模式】" not in prompts.build_instructions(db)
    plan_text = prompts.build_instructions(db, plan_mode=True)
    assert "【计划模式】" in plan_text
    assert "必须调用 propose_plan" in plan_text
    assert "禁止直接文本答复" in plan_text


def test_user_prefix_contains_time_and_state(db):
    from zhishi.domain.tasks import service as ts
    from zhishi.domain.tasks.schemas import TaskCreate
    ts.create_task(db, TaskCreate(title="逾期测试", status="todo"))
    prefix = prompts.build_user_message_prefix(db)
    assert "当前时间" in prefix and "任务" in prefix
    assert prompts.TIME_MARK in prefix  # 前缀以时间块开头


def test_builtin_skills_seeded_and_injected(db):
    prompts.seed_builtin_skills(db)
    text = prompts.build_instructions(db)
    assert "任务、提醒与日程" in text     # 内置技能内容进入 instructions


def test_enabled_user_skill_injected(db):
    from zhishi.domain.models import AISkill
    db.add(AISkill(name="我的规则", description="d", content="回复必须用中文",
                   enabled=True, is_builtin=False)); db.commit()
    text = prompts.build_instructions(db)
    assert "回复必须用中文" in text
