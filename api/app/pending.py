"""Track in-flight correction tasks so ending a conversation can wait for them briefly."""

import asyncio
from collections import defaultdict
from collections.abc import Coroutine
from typing import Any
from uuid import UUID

_tasks: dict[UUID, set[asyncio.Task[None]]] = defaultdict(set)


def spawn(conversation_id: UUID, coro: Coroutine[Any, Any, None]) -> None:
    """Run `coro` in the background, holding a reference until it finishes."""
    task = asyncio.create_task(coro)
    tasks = _tasks[conversation_id]
    tasks.add(task)

    def _done(t: asyncio.Task[None]) -> None:
        tasks.discard(t)
        if not tasks:
            _tasks.pop(conversation_id, None)

    task.add_done_callback(_done)


async def wait_for_corrections(conversation_id: UUID, wait_seconds: float) -> None:
    """Wait up to `wait_seconds` for the conversation's pending corrections to land."""
    tasks = set(_tasks.get(conversation_id, ()))
    if tasks:
        await asyncio.wait(tasks, timeout=wait_seconds)
