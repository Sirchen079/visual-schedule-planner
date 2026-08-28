from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AIConfig, AISkill
from app.schemas import AISkillCreate, AISkillImport, AISkillUpdate


# 内置 skill：随版本种子注入，始终生效、不进用户视图、不可被用户删除/修改。
# 内容承载「帮用户做事的领域流程规则」，prompt 不再硬编码这些规则。
# 种子按 name 幂等 upsert（强制覆盖内置内容，保证随版本升级）。
BUILTIN_SKILLS: list[dict[str, str]] = [
    {
        "name": "内置·任务、提醒与日程",
        "description": "任务/提醒/日程的领域行为规则（系统内置，始终生效）",
        "content": (
            "【任务、提醒与日程】\n"
            "- 提醒在当前系统中用任务的 due_date 表达；「提醒我做某事」优先调用 create_reminder。\n"
            "- 任务支持精确时刻与多次提醒：due_time 为 \"HH:MM\"（配合 due_date），"
            "remind_offsets 为提前提醒分钟数组（如 [0,30,1440] 表示截止时/提前 30 分/提前 1 天）。\n"
            "- 任务支持重复规则：recur_rule 取值 none/daily/weekdays/weekly/monthly；"
            "用户说每天/每个工作日/每周/每月重复时设置对应规则。\n"
            "- 拆分任务时创建真实子任务（create_subtasks 或 create_task 带 subtask_titles），不要只写进 notes。\n"
            "- 日程：list_day_schedule 看当天安排，list_month_schedule 看整月压力，"
            "assign_task_to_day 把任务安排到某天。\n"
            "- 规划质量准则：\n"
            "  1) 创建或评估任务时尽量给出 estimated_minutes（预估分钟）；超过 120 分钟的任务先拆解再排程；\n"
            "  2) 排程前先查当日负载（任务数与预估总时长），单日建议不超过 6 个任务、深度工作不超过 4 小时；\n"
            "  3) 拆解任务用 create_subtasks：每个子任务动词开头、30-90 分钟可完成、有明确产出物，禁止空泛步骤；\n"
            "  4) 截止日前留缓冲：大任务的计划完成日至少比截止日早 1 天；\n"
            "  5) 复盘或给排程建议前先用 get_time_stats 看最近投入与预估偏差，用数据说话。"
        ),
    },
    {
        "name": "内置·资料与附件",
        "description": "资料库与对话附件的关联/保存规则（系统内置，始终生效）",
        "content": (
            "【资料与附件】\n"
            "- 资料关联：已有任务用 attach_file_to_task；新建任务/提醒可在参数里带 file_ids 或 "
            "attachment_ids，后端自动关联。\n"
            "- 对话附件可用 save_attachment_to_library 保存到资料库；无法判断资料归属时先 list_tasks 查看。\n"
            "- 通过联网搜索找到的外部资料用 import_web_resources 导入（需用户确认）；"
            "视频教程等保存为 video 链接资料。"
        ),
    },
    {
        "name": "内置·习惯、目标、日记与计时",
        "description": "习惯打卡/OKR/日记/番茄钟的行为规则（系统内置，始终生效）",
        "content": (
            "【习惯、目标、日记与计时】\n"
            "- 习惯打卡用 check_in_habit，新建习惯用 create_habit。\n"
            "- 记日记、写总结、记录心情用 write_journal。\n"
            "- 长期目标/OKR 用 list_goals 查看、create_goal 新建、update_kr_progress 更新手动类关键结果。\n"
            "- 专注/番茄钟用 start_timer 开始、stop_timer 结束。"
        ),
    },
    {
        "name": "内置·能力扩展",
        "description": "自助创建 skill 与配置 MCP 服务器的规则（系统内置，始终生效）",
        "content": (
            "【能力扩展（skill 与 MCP 自助配置）】\n"
            "- 用户发来希望固化为工作规则的文档/信息时，用 create_skill 整理成 skill（需用户确认后创建）。\n"
            "- 用户希望接入外部工具服务器时，用 create_mcp_server 配置 MCP（stdio 会执行本地命令，"
            "属高敏感操作，需用户确认；创建后提示用户到 MCP 面板测试连接）。"
        ),
    },
]


def _assert_name_available(db: Session, name: str, *, exclude_id: int | None = None) -> None:
    """name 与任何现存 skill（含内置）冲突时抛 ValueError（路由映射 409）。"""
    stmt = select(AISkill).where(AISkill.name == name)
    if exclude_id is not None:
        stmt = stmt.where(AISkill.id != exclude_id)
    if db.execute(stmt).scalars().first() is not None:
        raise ValueError(f"skill 名称已存在：{name}")


def list_skills(db: Session) -> list[AISkill]:
    """用户可见的 skill（排除内置）。"""
    return list(
        db.execute(
            select(AISkill).where(AISkill.is_builtin.is_(False)).order_by(AISkill.updated_at.desc())
        ).scalars().all()
    )


def list_builtin_skills(db: Session) -> list[AISkill]:
    return list(
        db.execute(select(AISkill).where(AISkill.is_builtin.is_(True))).scalars().all()
    )


def seed_builtin_skills(db: Session) -> None:
    """幂等种子内置 skill：只 upsert 内置行（不劫持同名用户 skill），再清理重名。"""
    for item in BUILTIN_SKILLS:
        existing = db.execute(
            select(AISkill).where(AISkill.name == item["name"], AISkill.is_builtin.is_(True))
        ).scalars().first()
        if existing is None:
            db.add(
                AISkill(
                    name=item["name"],
                    description=item["description"],
                    content=item["content"],
                    enabled=True,
                    is_builtin=True,
                )
            )
        else:
            existing.description = item["description"]
            existing.content = item["content"]
            existing.is_builtin = True
            existing.enabled = True
    db.commit()
    _dedupe_skill_names(db)


def _dedupe_skill_names(db: Session) -> None:
    """清理存量重名：内置优先保留原名，用户 skill 与内置/互相重名时改名 '原名 (n)'。幂等。"""
    seen: set[str] = set()
    rows = db.execute(
        select(AISkill).order_by(AISkill.is_builtin.desc(), AISkill.id)
    ).scalars().all()
    for skill in rows:
        if skill.name not in seen:
            seen.add(skill.name)
            continue
        n = 2
        new_name = f"{skill.name[:90]} ({n})"
        while new_name in seen:
            n += 1
            new_name = f"{skill.name[:90]} ({n})"
        skill.name = new_name
        seen.add(new_name)
    db.commit()


def create_skill(db: Session, payload: AISkillCreate) -> AISkill:
    _assert_name_available(db, payload.name.strip())
    skill = AISkill(**payload.model_dump())
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return skill


def import_skill(db: Session, payload: AISkillImport) -> AISkill:
    suffix = Path(payload.filename).suffix.lower()
    if suffix not in {".md", ".txt"}:
        raise ValueError("只支持 .md / .txt skill")
    name = Path(payload.filename).stem or "自定义 skill"
    if db.execute(select(AISkill).where(AISkill.name == name)).scalars().first() is not None:
        raise ValueError("与已有 skill 同名，请重命名文件后再导入")
    return create_skill(
        db,
        AISkillCreate(
            name=name,
            description="导入的自定义 skill",
            content=payload.content,
        ),
    )


def update_skill(db: Session, skill_id: int, payload: AISkillUpdate) -> AISkill | None:
    skill = db.get(AISkill, skill_id)
    if skill is None:
        return None
    if skill.is_builtin:
        raise ValueError("内置 skill 不可修改")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        _assert_name_available(db, data["name"].strip(), exclude_id=skill_id)
    for field, value in data.items():
        setattr(skill, field, value)
    db.commit()
    db.refresh(skill)
    return skill


def delete_skill(db: Session, skill_id: int) -> bool | None:
    """三态：None=不存在 / False=内置拒绝 / True=已删。"""
    skill = db.get(AISkill, skill_id)
    if skill is None:
        return None
    if skill.is_builtin:
        return False
    for config in db.execute(
        select(AIConfig).where(AIConfig.active_skill_id == skill_id)
    ).scalars().all():
        config.active_skill_id = None
    db.delete(skill)
    db.commit()
    return True


def enable_skill(db: Session, skill_id: int) -> AISkill | None:
    """启用某条用户 skill（同时停用其它用户 skill；内置 skill 不参与单选）。"""
    skill = db.get(AISkill, skill_id)
    if skill is None:
        return None
    if skill.is_builtin:
        raise ValueError("内置 skill 不参与启用")
    for row in db.execute(
        select(AISkill).where(AISkill.is_builtin.is_(False))
    ).scalars().all():
        row.enabled = row.id == skill_id
    for config in db.execute(
        select(AIConfig).where(AIConfig.enabled.is_(True))
    ).scalars().all():
        config.active_skill_id = skill_id
    db.commit()
    db.refresh(skill)
    return skill


def disable_all_skills(db: Session) -> None:
    """停用全部用户 skill，并清掉所有配置的 active_skill_id 指针。"""
    for row in db.execute(
        select(AISkill).where(AISkill.is_builtin.is_(False))
    ).scalars().all():
        row.enabled = False
    for config in db.execute(select(AIConfig)).scalars().all():
        config.active_skill_id = None
    db.commit()


def builtin_skill_text(db: Session) -> str:
    """内置规则文本（始终全量注入，权重最高）。"""
    builtins = list_builtin_skills(db)
    return "\n\n".join(s.content for s in builtins if s.content)


def user_skill_text(db: Session, config: AIConfig | None) -> str:
    """用户激活的 skill 文本（单选：config.active_skill_id 优先，否则 enabled 的用户 skill）。

    陈旧指针（skill 已停用/指向内置）不生效，落兜底；兜底查询多条 enabled 时取最近更新者。
    """
    skill = None
    if config and config.active_skill_id:
        candidate = db.get(AISkill, config.active_skill_id)
        if candidate is not None and not candidate.is_builtin and candidate.enabled:
            skill = candidate
    if skill is None:
        skill = db.execute(
            select(AISkill)
            .where(AISkill.is_builtin.is_(False), AISkill.enabled.is_(True))
            .order_by(AISkill.updated_at.desc(), AISkill.id.desc())
            .limit(1)
        ).scalars().first()
    return skill.content if skill else ""
