from app.services import app_setting_service


def test_list_settings_returns_defaults(client):
    body = client.get("/settings").json()
    assert body["assistant_float_enabled"] == "false"
    assert body["close_button_behavior"] == "minimize"


def test_update_settings_persists_and_returns_all(client):
    resp = client.put(
        "/settings",
        json={
            "settings": {
                "assistant_float_enabled": "true",
                "close_button_behavior": "ask",
            }
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["assistant_float_enabled"] == "true"
    assert body["close_button_behavior"] == "ask"

    # 再次读取应已持久化
    body = client.get("/settings").json()
    assert body["assistant_float_enabled"] == "true"
    assert body["close_button_behavior"] == "ask"


def test_get_setting_falls_back_to_default(db_session):
    assert app_setting_service.get_setting(db_session, "close_button_behavior") == "minimize"
    assert app_setting_service.get_setting(db_session, "assistant_float_enabled") == "false"


def test_get_setting_returns_stored_value(db_session):
    app_setting_service.set_setting(db_session, "assistant_float_enabled", "true")
    assert app_setting_service.get_setting(db_session, "assistant_float_enabled") == "true"


def test_list_settings_merges_defaults_and_stored(db_session):
    app_setting_service.set_setting(db_session, "close_button_behavior", "quit")
    merged = app_setting_service.list_settings(db_session)
    assert merged["close_button_behavior"] == "quit"
    # 未写入的键仍带默认值
    assert merged["assistant_float_enabled"] == "false"


def test_update_settings_overwrites(db_session):
    app_setting_service.set_setting(db_session, "close_button_behavior", "quit")
    merged = app_setting_service.update_settings(
        db_session, {"close_button_behavior": "minimize"}
    )
    assert merged["close_button_behavior"] == "minimize"
