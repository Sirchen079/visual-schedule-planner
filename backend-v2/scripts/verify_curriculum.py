"""Frozen v2.6 upgrade, content insertion/replacement and citation/history acceptance."""
import argparse
import tempfile
from pathlib import Path

from verify_learning import seed
from verify_ledger import request, start, stop


def verify(exe, previous_exe=None):
    root = Path(tempfile.mkdtemp(prefix='zhishi-curriculum-frozen-'))
    print(f'CURRICULUM_CHECK_ROOT={root}', flush=True)
    proc, log, port = start(previous_exe or exe, root, 'seed-previous')
    try:
        base, source, original = seed(port)
    finally:
        stop(proc, log, port)
    proc, log, port = start(exe, root, 'upgraded')
    try:
        before = request(port, base)
        assert before['tasks'] == original['tasks']
        target = before['tasks'][1]
        draft = {'version':2,'mode':'insert_before','target_link_id':target['id'],
            'rationale':'Practice foundations before the original experiment.',
            'steps':[{'title':'Foundations practice','outcome':'Explain one small example','minutes':45}]}
        plan = request(port, base+'/revisions','POST',draft,201)
        assert len(request(port, '/api/tasks')) == 2 and not plan['revision']['moved_manual']
        request(port, f'/api/research/plans/{plan["id"]}/apply','POST')
        detail = request(port, base)
        assert detail['tasks'][0] == original['tasks'][0] and detail['tasks'][2] == target
        assert [t['title'] for t in detail['tasks']] == [original['tasks'][0]['title'],'Foundations practice',target['title']]
        material = request(port, f'/api/materials/{source["library_file_id"]}')
        replacement = {'version':3,'mode':'replace','target_link_id':target['id'],
            'rationale':'Replace the untouched experiment with two gradual steps.',
            'steps':[{'title':'Gradual experiment','outcome':'Record one variable at a time','minutes':90,
                'source_refs':[{'source_id':source['id'],'part':1,'revision':material['document']['revision'],
                                'quote':'Read the concepts'}]}]}
        request(port, base+'/revisions','POST',replacement,409)
        replacement['movable_task_link_ids'] = [target['id']]
        plan = request(port, base+'/revisions','POST',replacement,201)
        assert plan['revision']['before_task'] == target and len(plan['revision']['moved_manual']) == 1
        assert len(request(port, '/api/tasks')) == 3
        applied = request(port, f'/api/research/plans/{plan["id"]}/apply','POST')
        assert request(port, f'/api/research/plans/{plan["id"]}/apply','POST') == applied
        assert applied['result']['new_tasks'] == 1 and applied['result']['replaced_tasks'] == 1
        detail = request(port, base)
        assert detail['project']['total_tasks'] == 4 and detail['project']['completed_tasks'] == 1
        assert detail['tasks'][2]['task_id'] == target['task_id']
        assert detail['tasks'][2]['source_refs'][0]['quote'] == 'Read the concepts'
        assert detail['tasks'][0] == original['tasks'][0]
        assert len(request(port, base+'/plans')['items']) == 3
        reordered = request(port, base+'/replan','POST',{'version':4},201)
        assert [u['title'] for u in reordered['units']] == [t['title'] for t in detail['tasks'][1:]]
        # Real study activity after a preview must prevent overwriting it.
        changed = request(port, f'/api/tasks/{detail["tasks"][2]["task_id"]}','PATCH',{'notes':'My actual experimental observations.'})
        assert changed['notes'] == 'My actual experimental observations.'
        request(port, f'/api/research/plans/{reordered["id"]}/apply','POST',expected=409)
        final = request(port, base)
        print('CURRICULUM_UPGRADE_INSERT_REPLACE_CITATION_MANUAL_HISTORY_PASS',flush=True)
    finally:
        stop(proc, log, port)
    proc, log, port = start(exe, root, 'restart')
    try:
        assert request(port, base)['tasks'] == final['tasks']
        historical = request(port, f'/api/research/plans/{plan["id"]}')
        assert historical['revision']['before_task'] == target
        assert historical['units'][1]['source_refs'][0]['quote'] == 'Read the concepts'
    finally:
        stop(proc, log, port)
    print('CURRICULUM_FROZEN_PASS: v2.6 upgrade, insertion order, manual permission, same task identity, split, verified citation, history, stale rejection, restart',flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('exe',type=Path)
    parser.add_argument('--previous-exe',type=Path)
    args = parser.parse_args()
    verify(args.exe.resolve(),args.previous_exe.resolve() if args.previous_exe else None)
