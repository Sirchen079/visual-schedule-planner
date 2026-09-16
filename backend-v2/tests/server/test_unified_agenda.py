"""日历与今日共享真实安排，覆盖排期、截止、子任务及后续编辑。"""
from fastapi.testclient import TestClient
from zhishi.server.app import create_app


def test_agenda_and_today_follow_task_lifecycle(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        task = c.post('/api/tasks', json={
            'title': '准备汇报', 'start_date': '2032-01-14T00:00:00',
            'due_date': '2032-01-16T00:00:00', 'due_time': '18:00',
        }).json()
        task_id = task['id']
        sub = c.post(f'/api/tasks/{task_id}/subtasks', json={'title': '整理数据'}).json()
        entry = c.post('/api/schedule/entries', json={
            'task_id': task_id, 'date': '2032-01-16', 'start_time': '09:00', 'end_time': '10:00',
        }).json()
        event = c.post('/api/schedule/events', json={
            'title': '例会', 'date': '2032-01-16', 'start_time': '09:00', 'end_time': '10:00',
            'recur_rrule': 'FREQ=DAILY;COUNT=2',
        }).json()

        def agenda():
            response = c.get('/api/schedule/agenda?start=2032-01-14&end=2032-01-17')
            assert response.status_code == 200
            return response.json()

        items = agenda()
        assert [i['date'] for i in items if i['kind'] == 'event'] == ['2032-01-16', '2032-01-17']
        assert {i['kind'] for i in items} == {'event', 'task', 'task_due', 'task_start'}
        assert next(i for i in items if i['kind'] == 'task')['entry_id'] == entry['id']
        assert next(i for i in items if i['kind'] == 'task_due')['end_time'] is None
        day = c.get('/api/schedule/day?date=2032-01-16').json()['items']
        assert day == [i for i in items if i['date'] == '2032-01-16']
        assert all(i['subtasks'] == [{'id': sub['id'], 'title': '整理数据', 'done': False}]
                   for i in items if i['task_id'] == task_id)

        assert c.patch(f'/api/tasks/{task_id}', json={
            'title': '完成汇报', 'due_date': '2032-01-17T00:00:00',
        }).status_code == 200
        assert c.patch(f'/api/schedule/entries/{entry["id"]}', json={
            'date': '2032-01-17', 'start_time': '22:00', 'end_time': '23:00',
        }).status_code == 200
        c.patch(f'/api/tasks/{task_id}/subtasks/{sub["id"]}', json={'done': True})
        changed = [i for i in agenda() if i['task_id'] == task_id and i['date'] == '2032-01-17']
        assert {i['kind'] for i in changed} == {'task', 'task_due'}
        assert all(i['title'] == '完成汇报' and i['subtasks'][0]['done'] for i in changed)
        assert all(i['task_status'] == 'done' for i in changed)
        assert all(i['task_id'] is None for i in c.get('/api/schedule/day?date=2032-01-16').json()['items'])

        c.delete(f'/api/schedule/entries/{entry["id"]}')
        assert not any(i['kind'] == 'task' for i in agenda())
        c.delete(f'/api/tasks/{task_id}')
        assert all(i['event_id'] == event['id'] for i in agenda())
        c.post(f'/api/tasks/{task_id}/restore')
        assert any(i['kind'] == 'task_due' for i in agenda())


def test_agenda_keeps_untimed_tasks_and_range_includes_second_week(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        task = c.post('/api/tasks', json={'title': '拆解后的任务'}).json()
        for day in ['2032-01-01', '2032-01-14']:
            c.post('/api/schedule/entries', json={'task_id': task['id'], 'date': day})
        c.post('/api/tasks', json={'title': '没有任何日期'})
        response = c.get('/api/schedule/agenda?start=2032-01-01&end=2032-01-14')
        assert response.status_code == 200
        items = response.json()
        assert len(items) == 2
        assert all(i['start_time'] is None and i['end_time'] is None for i in items)
        loads = c.get('/api/schedule/range?start=2032-01-01&end=2032-01-14').json()
        assert len(loads) == 14 and loads['2032-01-14']['items'][0]['task_id'] == task['id']
        assert len(c.get('/api/schedule/range?start=2032-01-01&days=7').json()) == 7
        assert c.get('/api/schedule/agenda?start=2032-01-14&end=2032-01-01').status_code == 422
        assert c.get('/api/schedule/range?start=2032-01-14&end=2032-01-01').status_code == 422


def test_task_detail_lists_all_schedule_dates_and_hides_deleted_task(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        task = c.post('/api/tasks', json={'title': '查看完整排期'}).json()
        other = c.post('/api/tasks', json={'title': '其他任务'}).json()
        for day in ['2020-01-01', '2035-12-31']:
            c.post('/api/schedule/entries', json={
                'task_id': task['id'], 'date': day, 'note': f'{day} 的详细安排',
            })
        c.post('/api/schedule/entries', json={'task_id': other['id'], 'date': '2035-12-31'})
        url = f'/api/schedule/tasks/{task["id"]}/entries'
        response = c.get(url)
        assert response.status_code == 200
        assert [row['date'] for row in response.json()] == ['2020-01-01', '2035-12-31']
        assert response.json()[1]['note'] == '2035-12-31 的详细安排'
        c.delete(f'/api/tasks/{task["id"]}')
        assert c.get(url).status_code == 404
        assert c.get('/api/schedule/tasks/999999/entries').status_code == 404
