"""Simple in-process pub/sub keyed by task_id."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass
class OrchEvent:
    type: str
    task_id: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_wire(self) -> dict[str, Any]:
        return {"type": self.type, "task_id": self.task_id, "payload": self.payload}


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[asyncio.Queue]] = {}

    def subscribe(self, task_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subs.setdefault(task_id, []).append(q)
        return q

    def unsubscribe(self, task_id: str, q: asyncio.Queue) -> None:
        if task_id in self._subs:
            try:
                self._subs[task_id].remove(q)
            except ValueError:
                pass
            if not self._subs[task_id]:
                self._subs.pop(task_id, None)

    async def publish(self, event: OrchEvent) -> None:
        for q in list(self._subs.get(event.task_id, [])):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:  # pragma: no cover
                pass
