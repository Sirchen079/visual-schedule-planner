import json

from fastapi.testclient import TestClient
from pydantic_ai.messages import ToolReturnPart, UserPromptPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from tests.server.test_attachments import _parse_sse, _seed_enabled_config
from zhishi.server.app import create_app
from zhishi.server.routes import ai


def test_material_api_cursor_search_and_deleted_file(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        body = '前文。'*10000+'最后要求：提交评估结果。'
        file = c.post('/api/files',files={'file':('long.txt',body.encode(),'text/plain')}).json()
        first = c.get(f"/api/materials/{file['id']}").json()
        assert len(first['parts']) == 3 and first['next_call']['args']['part'] == 4
        hit = c.get('/api/materials/search',params={'query':'最后要求','file_id':file['id']}).json()['hits'][0]
        tail = c.get(f"/api/materials/{file['id']}",params={'part':hit['part'],'revision':hit['revision']}).json()
        assert '评估结果' in tail['parts'][0]['text']
        assert tail['document']['indexed_chars'] == len(body)
        assert c.get(f"/api/materials/{file['id']}",params={'revision':'wrong'}).status_code == 409
        assert c.get(f"/api/materials/{file['id']}",params={'count':20}).status_code == 422
        assert c.get('/api/materials/search',params={'query':''}).status_code == 422
        assert c.delete(f"/api/files/{file['id']}").status_code == 204
        assert c.get(f"/api/materials/{file['id']}").status_code == 404


def test_corrupt_document_returns_readable_failure_and_keeps_other_search_results(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        failed = c.post('/ai/attachments',files={'file':('broken.docx',b'not a zip','application/octet-stream')})
        assert failed.status_code == 201 and failed.json()['parse_status'] == 'failed'
        assert c.get(f"/api/materials/{failed.json()['file_id']}").status_code == 422
        c.post('/api/files',files={'file':('good.txt','正常材料里的关键词'.encode(),'text/plain')})
        result = c.get('/api/materials/search',params={'query':'关键词'}).json()
        assert result['hits'] and len(result['errors']) == 1


def test_attachment_guidance_and_fallible_agent_find_late_material_without_reupload(tmp_path, monkeypatch):
    rounds = 0
    fid = None
    async def stream(messages, info):
        nonlocal rounds
        rounds += 1
        returns = [p for m in messages for p in m.parts if isinstance(p,ToolReturnPart)]
        latest = json.loads(returns[-1].content) if returns else None
        if rounds == 1:
            prompt = '\n'.join(p.content for m in messages for p in m.parts if isinstance(p,UserPromptPart) and isinstance(p.content,str))
            assert '以下为开头预览' in prompt and 'read_material' in prompt and 'search_materials' in prompt
            assert '最终要求：9月30日' not in prompt
            name,args = 'search_materials',{'query':'最终要求','file_id':fid}
        elif rounds == 2:
            hit = latest['hits'][0]
            assert hit['part'] > 15
            name,args = 'read_material',{'file_id':fid,'part':999999}
        elif rounds == 3:
            assert latest['code'] == 'material_conflict'
            name,args = latest['next_call']['tool'],latest['next_call']['args']
        elif rounds == 4:
            assert latest['document']['file_id'] == fid
            name,args = 'search_materials',{'query':'最终要求','file_id':fid}
        elif rounds == 5:
            name,args = latest['hits'][0]['next_call']['tool'],latest['hits'][0]['next_call']['args']
        else:
            assert '最终要求：9月30日前完成研究报告' in latest['parts'][0]['text']
            assert latest['parts'][0]['citation'] and latest['document']['partial'] is False
            yield '原文最后一段要求9月30日前完成研究报告。'
            return
        yield {0:DeltaToolCall(name=name,json_args=json.dumps(args),tool_call_id=f'material-{rounds}')}
    monkeypatch.setattr(ai,'build_model',lambda *a,**k:FunctionModel(stream_function=stream))
    with TestClient(create_app(data_dir=tmp_path)) as c:
        _seed_enabled_config(c)
        body = '前文知识。'*8000+'最终要求：9月30日前完成研究报告。'
        fid = c.post('/ai/attachments',files={'file':('long.txt',body.encode(),'text/plain')}).json()['file_id']
        events = _parse_sse(c.post('/ai/chat/stream',json={'message':'材料最后的要求是什么？','attachment_ids':[fid]}).text)
        assert not [e for e in events if e['type'] in ('run_error','tool_approval_requested')], events
        assert rounds == 6 and c.get('/api/tasks').json() == []
