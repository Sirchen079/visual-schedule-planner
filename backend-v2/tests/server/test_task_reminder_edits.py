from fastapi.testclient import TestClient

from zhishi.server.app import create_app


def test_patch_omission_null_and_reminder_validation(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as client:
        row = client.post('/api/tasks', json={"title":"测试", "due_date":"2099-01-01",
            "due_time":"09:00", "remind_offsets":[30, 0]}).json()
        url = f"/api/tasks/{row['id']}"
        kept = client.patch(url, json={"title":"更新标题"}).json()
        assert kept['due_time'] == '09:00' and kept['remind_offsets'] == [0, 30]
        assert client.patch(url, json={"due_time":"29:00"}).status_code == 422
        assert client.patch(url, json={"remind_offsets":[-30]}).status_code == 422
        cleared = client.patch(url, json={"due_date":None, "due_time":None, "remind_offsets":[]}).json()
        assert cleared['due_date'] is None and cleared['due_time'] is None
        assert client.get(url).json()['remind_offsets'] == []
