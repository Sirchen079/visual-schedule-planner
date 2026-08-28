def test_create_and_enable_skill(client):
    resp = client.post(
        "/ai/skills",
        json={
            "name": "论文规划",
            "description": "偏向科研任务拆解",
            "content": "把任务拆成可执行的小步骤。",
        },
    )
    assert resp.status_code == 201
    skill = resp.json()
    assert skill["enabled"] is False

    enabled = client.post(f"/ai/skills/{skill['id']}/enable")
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True


def test_import_skill_rejects_empty_content(client):
    resp = client.post(
        "/ai/skills/import",
        json={
            "filename": "empty.md",
            "content": "",
        },
    )
    assert resp.status_code == 422


def test_import_skill_rejects_unsupported_extension(client):
    resp = client.post(
        "/ai/skills/import",
        json={
            "filename": "skill.py",
            "content": "print('not executable')",
        },
    )
    assert resp.status_code == 400


# ---- 内置 skill 机制 ----


def test_seed_builtin_skills_is_idempotent(db_session):
    from app.services import ai_skill_service

    ai_skill_service.seed_builtin_skills(db_session)
    first = ai_skill_service.list_builtin_skills(db_session)
    assert len(first) == len(ai_skill_service.BUILTIN_SKILLS)
    # 再次种子：不新增，内容可被强制更新
    ai_skill_service.seed_builtin_skills(db_session)
    second = ai_skill_service.list_builtin_skills(db_session)
    assert len(second) == len(first)
    assert {s.name for s in second} == {s.name for s in first}


def test_list_skills_excludes_builtins(client, db_session):
    from app.services import ai_skill_service

    ai_skill_service.seed_builtin_skills(db_session)
    client.post("/ai/skills", json={"name": "我的规则", "content": "x"})
    visible = client.get("/ai/skills").json()
    names = [s["name"] for s in visible]
    assert "我的规则" in names
    assert all(not n.startswith("内置·") for n in names)  # 内置不进用户视图


def test_delete_and_enable_refuse_builtins(db_session):
    import pytest
    from app.models import AISkill
    from app.services import ai_skill_service

    ai_skill_service.seed_builtin_skills(db_session)
    builtin = ai_skill_service.list_builtin_skills(db_session)[0]
    # delete_skill 内置返回 False（三态：None 不存在 / False 内置 / True 已删）
    assert ai_skill_service.delete_skill(db_session, builtin.id) is False
    # enable_skill 内置抛 ValueError（路由映射 409）
    with pytest.raises(ValueError):
        ai_skill_service.enable_skill(db_session, builtin.id)
    # 内置仍存在且启用
    assert db_session.get(AISkill, builtin.id) is not None


def test_builtin_skill_text_always_returns_rules(db_session):
    from app.services import ai_skill_service

    ai_skill_service.seed_builtin_skills(db_session)
    text = ai_skill_service.builtin_skill_text(db_session)
    assert "任务、提醒与日程" in text
    assert "能力扩展" in text


def test_build_system_prompt_injects_builtin_rules_with_priority(db_session):
    from app.models import AIConfig
    from app.services import ai_prompt_service, ai_skill_service

    ai_skill_service.seed_builtin_skills(db_session)
    config = AIConfig(provider="openai_chat", model="m", api_key="k")
    prompt = ai_prompt_service.build_system_prompt(db_session, config)
    # 内置规则注入，带最高优先级声明
    assert "系统内置规则" in prompt
    assert "不得忽视" in prompt
    assert "任务、提醒与日程" in prompt
    # native 协议段仍在（工作准则）
    assert "工作准则" in prompt


def test_user_skill_stacks_after_builtin(db_session):
    from app.models import AIConfig
    from app.schemas import AISkillCreate
    from app.services import ai_prompt_service, ai_skill_service

    ai_skill_service.seed_builtin_skills(db_session)
    skill = ai_skill_service.create_skill(
        db_session,
        AISkillCreate(name="我的规则", content="每周五做复盘"),
    )
    ai_skill_service.enable_skill(db_session, skill.id)
    config = AIConfig(provider="openai_chat", model="m", api_key="k")
    prompt = ai_prompt_service.build_system_prompt(db_session, config)
    assert "系统内置规则" in prompt
    assert "用户自定义 skill" in prompt
    assert "每周五做复盘" in prompt


# ---- T1-T11：本次修复回归 ----


def _seed_and_user(db_session):
    from app.services import ai_skill_service

    ai_skill_service.seed_builtin_skills(db_session)
    return ai_skill_service


def test_t1_create_user_skill_with_builtin_name_rejected(client, db_session):
    """T1：创建与内置同名的用户 skill → 409。"""
    _seed_and_user(db_session)
    builtin_name = "内置·任务、提醒与日程"
    resp = client.post("/ai/skills", json={"name": builtin_name, "content": "x"})
    assert resp.status_code == 409


def test_t2_duplicate_user_skill_names_rejected(client, db_session):
    """T2：两条同名 / 重命名为已存在 / 导入同名 均 409（导入 400）。"""
    _seed_and_user(db_session)
    client.post("/ai/skills", json={"name": " dupA".strip(), "content": "x"})
    # 再建同名
    assert client.post("/ai/skills", json={"name": "dupA", "content": "y"}).status_code == 409
    # 改名为已存在
    first = client.post("/ai/skills", json={"name": "dupB", "content": "x"}).json()
    assert client.put(f"/ai/skills/{first['id']}", json={"name": "dupA"}).status_code == 409
    # 导入同名文件 → 400
    assert client.post(
        "/ai/skills/import", json={"filename": "dupA.md", "content": "z"}
    ).status_code == 400


def test_t3_update_builtin_rejected(client, db_session):
    """T3：更新内置 skill → 409；内置内容未变。"""
    from app.services import ai_skill_service

    ai_skill_service.seed_builtin_skills(db_session)
    builtin = ai_skill_service.list_builtin_skills(db_session)[0]
    original = builtin.content
    resp = client.put(f"/ai/skills/{builtin.id}", json={"content": "被篡改"})
    assert resp.status_code == 409
    db_session.refresh(builtin)
    assert builtin.content == original


def test_t5_seed_recovers_builtin_and_renames_colliding_user(db_session):
    """T5：脏库（用户 skill 与内置同名）跑 seed → 不崩；内置恢复；用户改名为 (2)。"""
    from app.models import AISkill
    from app.services import ai_skill_service

    builtin_name = ai_skill_service.BUILTIN_SKILLS[0]["name"]
    # 预置一条与内置同名的用户 skill（脏库）
    db_session.add(AISkill(name=builtin_name, content="用户的脏内容", is_builtin=False))
    db_session.commit()
    ai_skill_service.seed_builtin_skills(db_session)
    # 内置行内容已恢复为种子内容
    builtins = [s for s in db_session.query(AISkill).filter_by(name=builtin_name).all() if s.is_builtin]
    assert len(builtins) == 1
    assert builtins[0].content == ai_skill_service.BUILTIN_SKILLS[0]["content"]
    # 用户行被改名，仍 is_builtin=False
    renamed = db_session.query(AISkill).filter(AISkill.content == "用户的脏内容").one()
    assert renamed.is_builtin is False
    assert renamed.name.startswith(builtin_name[:30])
    assert renamed.name != builtin_name


def test_t6_execute_create_skill_rejects_builtin_name(db_session):
    """T6：_execute_create_skill payload name 命中内置 → 拒绝；内置未变。"""
    from app.services import ai_action_service, ai_skill_service

    ai_skill_service.seed_builtin_skills(db_session)
    builtin_name = ai_skill_service.BUILTIN_SKILLS[1]["name"]
    builtin = next(s for s in ai_skill_service.list_builtin_skills(db_session) if s.name == builtin_name)
    original = builtin.content
    ok, message = ai_action_service._execute_create_skill(
        db_session, {"name": builtin_name, "content": "覆盖内置"}
    )
    assert ok is False
    assert "换一个名称" in message
    db_session.refresh(builtin)
    assert builtin.content == original


def test_t7_stale_active_skill_id_falls_back(db_session):
    """T7：active_skill_id 指向 enabled=False 的 skill，另有 enabled 的 S2 → 返回 S2。"""
    from app.models import AIConfig
    from app.schemas import AISkillCreate
    from app.services import ai_skill_service

    ai_skill_service.seed_builtin_skills(db_session)
    s1 = ai_skill_service.create_skill(db_session, AISkillCreate(name="S1", content="内容一"))
    s2 = ai_skill_service.create_skill(db_session, AISkillCreate(name="S2", content="内容二"))
    ai_skill_service.enable_skill(db_session, s2.id)  # S2 enabled
    # 陈旧指针指向已停用的 S1
    config = AIConfig(provider="openai_chat", model="m", api_key="k", active_skill_id=s1.id, enabled=True)
    db_session.add(config)
    db_session.commit()
    assert "内容二" == ai_skill_service.user_skill_text(db_session, config)


def test_t8_multiple_enabled_does_not_crash(db_session):
    """T8：两条 enabled 用户 skill → user_skill_text 不抛异常，返回最近更新者。"""
    from app.models import AISkill
    from app.services import ai_skill_service

    ai_skill_service.seed_builtin_skills(db_session)
    db_session.add_all([
        AISkill(name="E1", content="c1", enabled=True, is_builtin=False),
        AISkill(name="E2", content="c2", enabled=True, is_builtin=False),
    ])
    db_session.commit()
    text = ai_skill_service.user_skill_text(db_session, None)
    assert text in {"c1", "c2"}


def test_t9_disable_all(client, db_session):
    """T9：POST /ai/skills/disable-all → 全停用 + 指针清空 + user_skill_text 空。"""
    from app.models import AIConfig
    from app.schemas import AISkillCreate
    from app.services import ai_skill_service

    ai_skill_service.seed_builtin_skills(db_session)
    s = ai_skill_service.create_skill(db_session, AISkillCreate(name="A", content="x"))
    ai_skill_service.enable_skill(db_session, s.id)
    db_session.add(AIConfig(provider="openai_chat", model="m", api_key="k", enabled=True))
    db_session.commit()
    resp = client.post("/ai/skills/disable-all")
    assert resp.status_code == 204
    assert all(not sk.enabled for sk in ai_skill_service.list_skills(db_session))
    assert all(c.active_skill_id is None for c in db_session.query(AIConfig).all())
    assert ai_skill_service.user_skill_text(db_session, None) == ""


def test_t10_content_too_long_rejected(client, db_session):
    """T10：content 超 20000 字 → 422（schema 校验）。"""
    _seed_and_user(db_session)
    resp = client.post("/ai/skills", json={"name": "太长", "content": "x" * 20001})
    assert resp.status_code == 422


def test_t11_dedupe_idempotent(db_session):
    """T11：连续两次 _dedupe_skill_names 第二次无改名。"""
    from app.models import AISkill
    from app.services import ai_skill_service

    db_session.add_all([
        AISkill(name="同名", content="a", is_builtin=False),
        AISkill(name="同名", content="b", is_builtin=False),
    ])
    db_session.commit()
    ai_skill_service._dedupe_skill_names(db_session)
    names_after_first = sorted(s.name for s in db_session.query(AISkill).all())
    ai_skill_service._dedupe_skill_names(db_session)
    names_after_second = sorted(s.name for s in db_session.query(AISkill).all())
    assert names_after_first == names_after_second
    assert len(set(names_after_first)) == 2  # 无重名残留
