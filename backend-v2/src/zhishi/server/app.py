"""应用工厂。进程契约（Electron 拉起约定，不可破坏）：
--port 参数、/health、/shutdown、ZHISHI_DATA_DIR、静态目录托管。"""
from __future__ import annotations
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from zhishi import __version__
from zhishi.infra.config import Settings
from zhishi.infra.database import create_all, make_engine, make_session_factory
from zhishi.infra.logsetup import setup_logging
from zhishi.infra.scheduler import Scheduler

log = logging.getLogger(__name__)

# 轻量幂等列迁移清单：create_all 只建新表不 ALTER 旧表，存量库靠这里补列。
_SCHEMA_PATCHES: list[tuple[str, str, str]] = [
    ('research_sources', 'superseded_by', 'ALTER TABLE research_sources ADD COLUMN superseded_by INTEGER'),
    ('events', 'remind_offsets', "ALTER TABLE events ADD COLUMN remind_offsets TEXT NOT NULL DEFAULT '[]'"),
    ('events', 'reminder_time', 'ALTER TABLE events ADD COLUMN reminder_time VARCHAR(5)'),
    ('notification_logs', 'dedupe_key', 'ALTER TABLE notification_logs ADD COLUMN dedupe_key VARCHAR(200)'),
    ('ai_configs', 'context_window', 'ALTER TABLE ai_configs ADD COLUMN context_window INTEGER'),
    ('ai_configs', 'max_output_tokens', 'ALTER TABLE ai_configs ADD COLUMN max_output_tokens INTEGER'),
    ('ai_configs', 'reasoning_effort', 'ALTER TABLE ai_configs ADD COLUMN reasoning_effort VARCHAR(16)'),
    ('ai_configs', 'input_modalities_json',
     "ALTER TABLE ai_configs ADD COLUMN input_modalities_json TEXT NOT NULL DEFAULT '[\"text\"]'"),
    ('notification_logs', 'target_path',
     "ALTER TABLE notification_logs ADD COLUMN target_path VARCHAR(300) NOT NULL DEFAULT ''"),
    ("library_files", "content_sha256",
     "ALTER TABLE library_files ADD COLUMN content_sha256 VARCHAR(64)"),
    ("mcp_servers", "trusted",
     "ALTER TABLE mcp_servers ADD COLUMN trusted BOOLEAN NOT NULL DEFAULT 0"),
    ("events", "repeat_note",
     "ALTER TABLE events ADD COLUMN repeat_note TEXT"),
]


def _ensure_schema(engine) -> None:
    """启动时对存量库幂等补列（单人 SQLite，无需 Alembic）。"""
    with engine.connect() as conn:
        for table, column, ddl in _SCHEMA_PATCHES:
            cols = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            if column not in cols:
                conn.exec_driver_sql(ddl)
        conn.exec_driver_sql('CREATE UNIQUE INDEX IF NOT EXISTS ux_notification_dedupe_key ON notification_logs(dedupe_key)')
        conn.commit()


def _origin_allowed(origin: str, host: str) -> bool:
    """Origin 与请求 Host 是否同源：host 不区分大小写，端口缺失按 scheme 补默认值。"""
    from urllib.parse import urlsplit
    try:
        o, h = urlsplit(origin), urlsplit(f"//{host}")
    except ValueError:
        return False
    if o.hostname is None or h.hostname is None:
        return False
    oport = o.port or (443 if o.scheme == "https" else 80)
    hport = h.port or 80
    return o.hostname.lower() == h.hostname.lower() and oport == hport


class OriginGuardMiddleware:
    """本地单机防护（替代原通配 CORS，B1 安全加固）：
    1) Host 钉死：请求 Host 的 hostname 必须在回环白名单（127.0.0.1/localhost/::1，
       环境变量 ZHISHI_TRUSTED_HOSTS 可覆盖，测试环境注入 testserver）——
       根治 DNS rebinding（攻击域名的 Host/Origin 一致也拦）；
    2) Origin 同源：带 Origin 且与 Host 不同源 → 403（防本机跨端口页面跨站读取）。
    同源请求与无 Origin 请求（Electron BrowserWindow 同源加载、curl）放行。"""

    def __init__(self, app, trusted_hosts: list[str] | None = None):
        self.app = app
        self.trusted_hosts = {h.lower() for h in (trusted_hosts or ["127.0.0.1", "localhost", "::1"])}

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = {k.decode("latin-1").lower(): v.decode("latin-1")
                       for k, v in scope.get("headers", [])}
            host = headers.get("host", "")
            from urllib.parse import urlsplit
            hostname = (urlsplit(f"//{host}").hostname or "").lower()
            if hostname not in self.trusted_hosts:
                resp = JSONResponse({"detail": "Host 不被允许（仅限本机回环访问）"},
                                    status_code=403)
                await resp(scope, receive, send)
                return
            origin = headers.get("origin")
            if origin and not _origin_allowed(origin, host):
                resp = JSONResponse({"detail": "Origin 不被允许（跨站请求已拦截）"},
                                    status_code=403)
                await resp(scope, receive, send)
                return
        await self.app(scope, receive, send)


def create_app(data_dir: Path | None = None, port: int | None = None) -> FastAPI:
    # 注意：routes 包里也有个 settings 模块会在下方 import 进本作用域，
    # 配置实例必须用别的名字（cfg），否则被遮蔽后真实启动路径会炸。
    cfg = Settings(port=port or 8000)
    root = (data_dir or cfg.data_root) / "v2"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        setup_logging(logs_dir=root / "logs", console=False)
        engine = make_engine(root / "backend.db")
        create_all(engine)
        _ensure_schema(engine)   # 幂等列迁移：旧库补新列（create_all 不做 ALTER）
        app.state.engine = engine
        app.state.session_factory = make_session_factory(engine)
        app.state.storage_root = root / "attachments"

        with app.state.session_factory() as session:
            from zhishi.agent.prompts import seed_builtin_skills
            seed_builtin_skills(session)   # 幂等：内置技能随版本更新，保留用户 enabled 选择
            from zhishi.agent.session_store import recover_interrupted
            recover_interrupted(session)

        scheduler = Scheduler()
        session_factory = app.state.session_factory

        async def scan_reminders() -> None:
            def _do() -> None:
                with session_factory() as session:
                    from zhishi.domain.notifications import record_due_reminders
                    record_due_reminders(session)
                    from zhishi.domain.ledger.bills import remind
                    remind(session)
            await asyncio.to_thread(_do)

        scheduler.add("reminder-scan", interval=30, coro_factory=scan_reminders)

        async def scan_followups() -> None:
            def _do() -> None:
                with session_factory() as session:
                    from zhishi.domain.followups import scan
                    scan(session)
            await asyncio.to_thread(_do)

        scheduler.add('secretary-followups', interval=300, coro_factory=scan_followups)

        async def scan_research_watches() -> None:
            def _do() -> None:
                with session_factory() as session:
                    from zhishi.domain.research.watches import scan
                    scan(session)
            await asyncio.to_thread(_do)

        scheduler.add('research-watches', interval=60, coro_factory=scan_research_watches)

        # 晨报/自动档：Scheduler 是固定间隔轮询，这里按「触发时刻自检 + 当日幂等」接线——
        # 每轮先看时刻是否已过触发点（晨报 07:00 / 自动档 08:00）且当日未产出，才真正执行；
        # 幂等由 reports.get_or_create_briefing / autopilot 的当日 ai_reports 记录保证。
        from zhishi.domain import autopilot, reports

        async def run_morning_briefing() -> None:
            def _do() -> None:
                with session_factory() as session:
                    if reports.should_run_briefing_now(session):
                        reports.run_briefing_job(session, datetime.now().date())
            await asyncio.to_thread(_do)

        async def run_autopilot_job() -> None:
            def _do() -> None:
                with session_factory() as session:
                    if autopilot.should_run_now(session):
                        autopilot.run_autopilot(session, reports.enabled_config(session),
                                                datetime.now().date())
            await asyncio.to_thread(_do)

        scheduler.add("morning-briefing", interval=600, coro_factory=run_morning_briefing)
        scheduler.add("autopilot", interval=600, coro_factory=run_autopilot_job)

        app.state.scheduler = scheduler
        app.state.active_runs: dict[int, str] = {}
        app.state.cancel_tokens: dict[str, object] = {}
        app.state.run_tasks = set()
        sched_task = await scheduler.start()
        yield
        await scheduler.stop(sched_task)
        for token in list(app.state.cancel_tokens.values()):
            token.cancel()
        if app.state.run_tasks:
            await asyncio.gather(*list(app.state.run_tasks), return_exceptions=True)
        engine.dispose()

    app = FastAPI(title="zhishi-backend", version=__version__, lifespan=lifespan)
    # 安全：Host 回环白名单 + Origin 同源防护（原 allow_origins=["*"] 通配 CORS 已移除；
    # bearer token 认证待新 Electron 壳支持请求头后引入）
    import os as _os
    _trusted = _os.environ.get("ZHISHI_TRUSTED_HOSTS", "127.0.0.1,localhost,::1")
    app.add_middleware(OriginGuardMiddleware,
                       trusted_hosts=[h.strip() for h in _trusted.split(",") if h.strip()])

    from zhishi.server.routes import (tasks, schedule, goals, habits, journal,
                                       focus, library, notifications, stats, settings, ical, ai,
                                        reports, ledger, bills, inbox, research, followups, materials, web_services, vision, ai_sessions)
    for module in (tasks, schedule, goals, habits, journal,
                   focus, library, notifications, stats, settings, ical, ai, reports, ledger, bills, inbox, research, followups, materials, web_services, vision, ai_sessions):
        app.include_router(module.router)

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "version": __version__}

    @app.post("/shutdown")
    async def shutdown() -> dict:
        app.state.shutdown_requested = True
        return {"ok": True}

    # Electron 进程契约：托管前端静态目录（Electron 旧壳加载 http://127.0.0.1:port/）。
    # 查找顺序：ZHISHI_FRONTEND_DIR 环境变量 > 仓库 frontend/dist > 数据根上级 frontend/dist；
    # 目录不存在则不挂载（纯 API 模式，前端项目就绪后放置目录即生效）。
    frontend_dir = _find_frontend_dir(data_dir or cfg.data_root)
    if frontend_dir is not None:
        from fastapi.staticfiles import StaticFiles
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

    return app


def _find_frontend_dir(data_dir: Path | None) -> Path | None:
    import os
    import sys
    candidates = []
    env = os.environ.get("ZHISHI_FRONTEND_DIR")
    if env:
        candidates.append(Path(env))
    # 打包自包含模式：spec 把 frontend/dist 收集进 _MEIPASS（脱仓库可用）
    if getattr(sys, "frozen", False):
        candidates.append(Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "frontend" / "dist")
    candidates.append(Path(__file__).resolve().parents[3] / "frontend" / "dist")
    if data_dir is not None:
        candidates.append(Path(data_dir).parent / "frontend" / "dist")
    for c in candidates:
        if (c / "index.html").exists():
            return c
    return None


def main() -> None:
    """PyInstaller 入口：python -m zhishi.server.app --port 8421"""
    import argparse, threading, time
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    app = create_app(port=args.port)
    server = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=args.port, log_config=None))

    def _watch() -> None:
        while True:
            if getattr(app.state, "shutdown_requested", False):
                server.should_exit = True
                return
            time.sleep(0.5)

    threading.Thread(target=_watch, daemon=True).start()
    server.run()


if __name__ == "__main__":
    main()
