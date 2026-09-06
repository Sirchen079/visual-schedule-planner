"""Independent periodic jobs: slow AI work must not delay reminders."""
from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Callable, Coroutine
from typing import Any

log = logging.getLogger(__name__)


class Scheduler:
    def __init__(self) -> None:
        self._jobs: dict[str, tuple[float, Callable[[], Coroutine[Any, Any, None]]]] = {}
        self._next_due: dict[str, float] = {}
        self._workers: dict[str, asyncio.Task] = {}
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._changed = asyncio.Event()

    def add(self, name: str, interval: float, coro_factory: Callable[[], Coroutine[Any, Any, None]]) -> None:
        if not math.isfinite(interval) or interval <= 0:
            raise ValueError('Job interval must be positive and finite')
        self._jobs[name] = (interval, coro_factory)
        self._changed.set()

    async def start(self) -> asyncio.Task:
        if self._task is not None and not self._task.done():
            return self._task
        self._stop.clear()
        self._changed.set()
        self._next_due.clear()
        self._task = asyncio.create_task(self._run())
        return self._task

    async def stop(self, task: asyncio.Task | None = None) -> None:
        self._stop.set()
        self._changed.set()
        target = task or self._task
        if target:
            target.cancel()
            try:
                await target
            except asyncio.CancelledError:
                pass

    async def _run_job(self, name: str) -> None:
        while not self._stop.is_set():
            interval, factory = self._jobs[name]
            try:
                await factory()
            except Exception:
                log.exception('scheduled job %s failed', name)
            # Delay starts after completion, so the same job never overlaps itself.
            self._next_due[name] = asyncio.get_running_loop().time() + interval
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except TimeoutError:
                pass

    async def _run(self) -> None:
        try:
            while not self._stop.is_set():
                self._changed.clear()
                for name in self._jobs:
                    if name not in self._workers:
                        self._workers[name] = asyncio.create_task(self._run_job(name), name=f'zhishi:{name}')
                await self._changed.wait()
        finally:
            workers = list(self._workers.values())
            for worker in workers:
                worker.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
            self._workers.clear()
