"""Bounded technical events. Never serialize log messages, exception text or request bodies."""
from __future__ import annotations

import json
import logging
import re
import secrets
import traceback
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

INSTANCE = secrets.token_hex(8)
_logger = logging.getLogger('zhishi_diagnostics')
_logger.propagate = False
_logger.setLevel(logging.INFO)


def symbol(value) -> str:
    value = str(value)
    return value[:120] if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.<>-]*', value) else 'redacted'


def error_details(exc) -> dict:
    frames = traceback.extract_tb(exc.__traceback__) if exc.__traceback__ else []
    return {'error_type': symbol(type(exc).__name__),
            'frames': [{'file': symbol(Path(f.filename).name), 'function': symbol(f.name), 'line': f.lineno}
                       for f in frames[-12:]]}


def record(kind: str, **fields) -> None:
    # Callers supply a fixed schema of technical values, never arbitrary data.
    try:
        _logger.info(json.dumps({'time': datetime.now(UTC).isoformat(),
                                'instance': INSTANCE, 'kind': kind, **fields}, ensure_ascii=False))
    except (OSError, TypeError, ValueError):
        pass  # Diagnostic failures must not interrupt the operation being diagnosed.


class TechnicalLogHandler(logging.Handler):
    def emit(self, entry):
        if entry.name == _logger.name:
            return
        if entry.levelno < logging.WARNING and not entry.name.startswith('zhishi.'):
            return
        fields = {'level': entry.levelname, 'module': symbol(entry.name),
                  'function': symbol(entry.funcName), 'line': entry.lineno}
        if entry.exc_info and entry.exc_info[1]:
            fields.update(error_details(entry.exc_info[1]))
        record('application', **fields)


def setup(logs_dir: Path) -> None:
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        target = str((logs_dir / 'diagnostics.jsonl').resolve())
    except OSError:
        return
    if any(getattr(h, 'baseFilename', None) == target for h in _logger.handlers):
        return
    for handler in list(_logger.handlers):
        _logger.removeHandler(handler)
        handler.close()
    try:
        handler = RotatingFileHandler(target, maxBytes=2 * 1024 * 1024, backupCount=3, encoding='utf-8')
    except OSError:
        return
    handler.setFormatter(logging.Formatter('%(message)s'))
    _logger.addHandler(handler)
    root = logging.getLogger()
    if not any(isinstance(h, TechnicalLogHandler) for h in root.handlers):
        root.addHandler(TechnicalLogHandler())
    from zhishi import __version__
    record('startup', version=__version__)


def snapshot(logs_dir: Path) -> tuple[list[dict], int]:
    """Read only the structured files created here; raw app.log stays on the device."""
    rows, skipped = [], 0
    paths = [logs_dir / ('diagnostics.jsonl' + suffix) for suffix in ('.3', '.2', '.1', '')]
    paths += [logs_dir / ('desktop-diagnostics.jsonl' + suffix) for suffix in ('.1', '')]
    for path in paths:
        try:
            # Bound reads even if a local file was unexpectedly replaced.
            with path.open('rb') as stream:
                content = stream.read(2 * 1024 * 1024 + 65536)
            for line in content.splitlines():
                try:
                    row = json.loads(line)
                    cleaned = export_record(row)
                    if cleaned:
                        rows.append(cleaned)
                except (ValueError, UnicodeError):
                    skipped += 1
        except FileNotFoundError:
            pass
    rows.sort(key=lambda row: row.get('time', ''))
    return rows[-5000:], skipped


def export_record(row) -> dict | None:
    """Enforce the export schema again, even for modified or older files."""
    if not isinstance(row, dict):
        return None
    kind = row.get('kind')
    if not isinstance(kind, str) or kind not in ('startup', 'shutdown', 'desktop', 'application', 'http', 'frontend', 'ai_request', 'ai_response'):
        return None
    out = {'kind': kind}
    for key in ('module', 'function',
                'error_type', 'method', 'outcome', 'event', 'asset'):
        value = row.get(key)
        if isinstance(value, str) and len(value) <= 120 and re.fullmatch(r'[A-Za-z0-9_.:+<>-]+', value):
            # Hex fingerprints, timestamps, code symbols only; no free-form messages.
            out[key] = value
    for key in ('instance', 'request_id', 'run', 'conversation', 'model', 'tools_fingerprint',
                'instructions_fingerprint', 'settings_fingerprint', 'service_fingerprint'):
        if isinstance(row.get(key), str) and re.fullmatch(r'[a-f0-9]{16,64}', row[key]):
            out[key] = row[key]
    if isinstance(row.get('version'), str) and re.fullmatch(r'\d+\.\d+\.\d+', row['version']):
        out['version'] = row['version']
    if row.get('protocol') in ('openai_compat', 'openai_responses', 'anthropic', 'other'):
        out['protocol'] = row['protocol']
    if row.get('level') in ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'):
        out['level'] = row['level']
    try:
        stamp = datetime.fromisoformat(row.get('time', ''))
        if stamp.tzinfo is not None:
            out['time'] = stamp.astimezone(UTC).isoformat(timespec='microseconds')
    except (ValueError, TypeError):
        pass
    for key in ('line', 'column', 'status_code', 'duration_ms', 'tool_count', 'part_count',
                'previous_part_count', 'shared_prefix_parts', 'input_tokens', 'output_tokens',
                'cache_read_tokens', 'cache_write_tokens'):
        value = row.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            out[key] = value
    for key in ('has_previous', 'tools_changed', 'instructions_changed', 'history_changed', 'settings_changed', 'service_changed'):
        if isinstance(row.get(key), bool):
            out[key] = row[key]
    route = row.get('route')
    if isinstance(route, str) and re.fullmatch(r'/[a-zA-Z0-9_/{}/-]{0,160}', route):
        out['route'] = route
    if isinstance(row.get('frames'), list):
        out['frames'] = [{'file': symbol(f.get('file', 'redacted')),
                          'function': symbol(f.get('function', 'redacted')),
                          'line': f['line']} for f in row['frames'][:12]
                         if isinstance(f, dict) and isinstance(f.get('line'), int)]
    return out


class DiagnosticHTTPMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        import time
        started, status = time.monotonic(), 500
        async def tracked_send(message):
            nonlocal status
            if message['type'] == 'http.response.start':
                status = message['status']
            await send(message)
        try:
            await self.app(scope, receive, tracked_send)
        except Exception as exc:
            record('application', level='ERROR', module='http', **error_details(exc))
            raise
        finally:
            route = getattr(scope.get('route'), 'path', '/unmatched')
            if not route.startswith('/api/diagnostics') and route != '/health':
                record('http', method=scope.get('method', 'UNKNOWN'), route=route,
                       status_code=status, duration_ms=int((time.monotonic() - started) * 1000))
