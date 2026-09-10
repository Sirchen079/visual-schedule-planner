"""One-click, local-only support bundle for the whole application."""
import io
import json
import platform
import zipfile
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from zhishi import __version__
from zhishi.infra.diagnostics import record, snapshot

router = APIRouter(prefix='/api/diagnostics', tags=['diagnostics'])


class FrontendEvent(BaseModel):
    model_config = ConfigDict(extra='forbid')
    event: Literal['window_error', 'unhandled_rejection', 'vue_error', 'resource_error']
    error_type: Literal['Error', 'TypeError', 'RangeError', 'ReferenceError', 'SyntaxError',
                        'URIError', 'EvalError', 'DOMException', 'Unknown'] = 'Unknown'
    asset: str = Field(default='', max_length=100, pattern=r'^(?:[A-Za-z0-9_-]+\.(?:js|css))?$')
    line: int = Field(default=0, ge=0, le=10000000)
    column: int = Field(default=0, ge=0, le=10000000)


@router.post('/frontend', status_code=204)
def frontend_event(body: FrontendEvent):
    record('frontend', **body.model_dump())
    return Response(status_code=204)


class DiagnosticZipResponse(Response):
    media_type = 'application/zip'


@router.get('/export', response_class=DiagnosticZipResponse,
            responses={200: {'content': {'application/zip': {'schema': {'type': 'string', 'format': 'binary'}}}}})
def export(request: Request):
    rows, skipped = snapshot(request.app.state.logs_dir)
    stamp = datetime.now(UTC)
    manifest = {'format_version': 1, 'app_version': __version__, 'exported_at': stamp.isoformat(),
                'os': platform.system(), 'os_release': platform.release(),
                'event_count': len(rows), 'skipped_incomplete_lines': skipped,
                'retention': 'Latest 5000 events; backend up to four 2 MiB files, desktop up to two 512 KiB files',
                'privacy': 'Technical fields only; no message text, request bodies, headers, query strings, keys, personal paths or attachments.'}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json', json.dumps(manifest, indent=2, ensure_ascii=False))
        archive.writestr('diagnostics.jsonl', '\n'.join(json.dumps(row, ensure_ascii=False) for row in rows))
        archive.writestr('README.txt',
            '知时诊断日志\n\n反馈问题时请附上此 ZIP，并说明发生时间、操作步骤、预期结果和实际结果。\n'
            '日志覆盖本版本启用记录后的启动、接口、后台告警/异常、前端异常和 AI 请求。\n'
            '为保护隐私，只保留错误类型、代码位置、接口模板、耗时和用量，不保留业务正文和原始异常消息。\n'
            '不包含原始 app.log、密钥、请求头、查询参数、聊天、附件或个人路径。\n'
            '缓存指纹只用于当前进程内比较；shared_prefix_parts 是结构片段数，不代表命中 token 数。\n'
            '模型用量来自服务商响应；结构稳定仍可能因服务商路由、过期或缓存策略出现未命中。\n'
            '日志有容量上限，过旧事件会轮换；升级前的问题可能需要复现后重新导出。\n')
    return Response(stream.getvalue(), media_type='application/zip', headers={
        'Content-Disposition': f'attachment; filename="zhishi-diagnostics-{stamp:%Y%m%d-%H%M%S}.zip"',
        'Cache-Control': 'no-store'})
