"""Frozen feedback and stage continuation, optionally upgrading an actual v2.5 fixture."""
# ruff: noqa: DTZ011 -- the app schedules local calendar days.
import argparse
import tempfile
from datetime import date, timedelta
from pathlib import Path

from verify_ledger import request, start, stop
from verify_research import upload


def seed(port):
    day = date.today() + timedelta(days=2)
    p = request(port, '/api/research/projects', 'POST', {'title':'Learning continuation acceptance',
        'objective':'Understand an example and independently explain its result', 'start_date':str(day),
        'daily_minutes':90, 'window_start':'18:00', 'window_end':'21:00'}, 201)
    base = f'/api/research/projects/{p["id"]}'
    source = request(port, base+'/materials', 'POST', {'file_id':upload(port)}, 201)
    plan = request(port, base+'/plans', 'POST', {'version':1, 'rationale':'Read, then try.', 'steps':[
        {'title':'Read an example', 'outcome':'Keep notes', 'minutes':45, 'source_ids':[source['id']]},
        {'title':'Try the example', 'outcome':'Save output', 'minutes':45, 'source_ids':[source['id']]}]}, 201)
    request(port, f'/api/research/plans/{plan["id"]}/apply', 'POST')
    detail = request(port, base)
    request(port, f'/api/tasks/{detail["tasks"][0]["task_id"]}', 'PATCH', {'status':'done'})
    manual = detail['tasks'][1]['slots'][0]
    request(port, f'/api/schedule/entries/{manual["id"]}', 'PATCH',
            {'date':str(day+timedelta(days=3)), 'start_time':'19:00', 'end_time':'19:45'})
    return base, source, request(port, base)


def verify(exe, previous_exe=None):
    root = Path(tempfile.mkdtemp(prefix='zhishi-learning-frozen-'))
    print(f'LEARNING_CHECK_ROOT={root}', flush=True)
    proc, log, port = start(previous_exe or exe, root, 'seed-previous' if previous_exe else 'seed')
    try:
        base, source, before = seed(port)
    finally:
        stop(proc, log, port)
    proc, log, port = start(exe, root, 'upgraded')
    try:
        detail = request(port, base)
        assert detail['project']['total_tasks'] == 2 and detail['project']['completed_tasks'] == 1
        assert detail['tasks'] == before['tasks']
        assert detail['feedback']['total'] == 0
        payload = {'version':2, 'request_key':'frozen-feedback', 'note':'I ran the example but need help understanding it.',
            'difficulty':'too_hard', 'actual_minutes':75, 'task_link_id':detail['tasks'][0]['id']}
        feedback = request(port, base+'/feedback', 'POST', payload, 201)
        assert request(port, base+'/feedback', 'POST', payload, 201)['id'] == feedback['id']
        request(port, base+'/feedback', 'POST', {**payload, 'note':'Different content'}, 409)
        assert request(port, base)['project']['completed_tasks'] == 1
        material = request(port, f'/api/materials/{source["library_file_id"]}')
        draft = {'version':3, 'rationale':'Use one concrete example to address the reported difficulty.',
            'feedback_ids':[feedback['id']], 'steps':[{'title':'Explain an example step by step',
                'outcome':'Write a reason for every step', 'minutes':45,
                'source_refs':[{'source_id':source['id'], 'part':1, 'revision':material['document']['revision'],
                                'quote':'Read the concepts'}]}]}
        request(port, base+'/extensions', 'POST', {**draft, 'feedback_ids':[999999]}, 409)
        plan = request(port, base+'/extensions', 'POST', draft, 201)
        assert request(port, base+'/extensions', 'POST', draft, 201)['id'] == plan['id']
        assert plan['feedback_ids'] == [feedback['id']] and len(request(port, '/api/tasks')) == 2
        assert (plan['assignments'][0]['date'], plan['assignments'][0]['start']) >= (
            before['tasks'][1]['slots'][0]['date'], before['tasks'][1]['slots'][0]['end'])
        applied = request(port, f'/api/research/plans/{plan["id"]}/apply', 'POST')
        assert request(port, f'/api/research/plans/{plan["id"]}/apply', 'POST') == applied
        detail = request(port, base)
        assert detail['tasks'][:2] == before['tasks'] and detail['project']['total_tasks'] == 3
        assert detail['tasks'][2]['source_refs'][0]['quote'] == 'Read the concepts'
        assert detail['feedback']['items'][0]['applied_plan_ids'] == [plan['id']]
        stale = request(port, base+'/extensions', 'POST', {**draft, 'version':4}, 201)
        request(port, base+f'/feedback/{feedback["id"]}/withdraw', 'POST', {'version':4})
        request(port, f'/api/research/plans/{stale["id"]}/apply', 'POST', expected=409)
        assert request(port, base+'/feedback')['total'] == 0
        assert len(request(port, '/api/tasks')) == 3
        print('LEARNING_UPGRADE_FEEDBACK_APPEND_CITATION_WITHDRAW_PASS', flush=True)
    finally:
        stop(proc, log, port)
    proc, log, port = start(exe, root, 'restart')
    try:
        detail = request(port, base)
        assert detail['project']['total_tasks'] == 3 and detail['project']['completed_tasks'] == 1
        assert detail['feedback']['total'] == 0 and detail['tasks'][:2] == before['tasks']
        assert request(port, f'/api/research/plans/{plan["id"]}')['feedback_ids'] == [feedback['id']]
    finally:
        stop(proc, log, port)
    print('LEARNING_FROZEN_PASS: old data upgrade, self-report, replay, feedback and source references, manual history preservation, append, withdrawal, stale rejection, restart', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('exe', type=Path)
    parser.add_argument('--previous-exe', type=Path)
    args = parser.parse_args()
    verify(args.exe.resolve(), args.previous_exe.resolve() if args.previous_exe else None)
