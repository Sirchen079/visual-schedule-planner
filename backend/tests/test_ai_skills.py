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
