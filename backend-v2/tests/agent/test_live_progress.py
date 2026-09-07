import asyncio
from contextlib import asynccontextmanager

from zhishi.agent.runtime import _node_stream_events


async def test_progress_is_visible_before_slow_connection_or_tool_completes():
    queue, release = asyncio.Queue(), asyncio.Event()
    class Node:
        @asynccontextmanager
        async def stream(self, ctx):
            queue.put_nowait({'type': 'stage_changed', 'stage': 'compacting'})
            await release.wait()
            async def stream():
                yield 'model-event'
            yield stream()
    stream = _node_stream_events(Node(), None, queue)
    assert await asyncio.wait_for(anext(stream), 1) == (None, {'type': 'stage_changed', 'stage': 'compacting'})
    assert not release.is_set()
    release.set()
    assert [item async for item in stream] == [('model-event', None)]


async def test_closing_progress_stream_cancels_pending_node_and_cleans_up():
    queue, closed = asyncio.Queue(), asyncio.Event()
    class Node:
        @asynccontextmanager
        async def stream(self, ctx):
            try:
                queue.put_nowait({'type': 'subagent_delta', 'delta': '正在检索'})
                await asyncio.Event().wait()
                yield None
            finally:
                closed.set()
    stream = _node_stream_events(Node(), None, queue)
    await asyncio.wait_for(anext(stream), 1)
    await stream.aclose()
    assert closed.is_set()
