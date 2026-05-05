"""Converse queue — FIFO per (task, role), drained by DispatchLoop on idle."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from orch_backend.models import RoleName


@dataclass
class ConverseMessage:
    id: str
    task_id: str
    role: RoleName
    message: str
    referenced_node_ids: list[str] = field(default_factory=list)


class ConverseQueue:
    """Pure in-memory FIFO; one deque per (task_id, role)."""

    def __init__(self) -> None:
        self._queues: dict[tuple[str, str], deque[ConverseMessage]] = {}

    def enqueue(self, msg: ConverseMessage) -> int:
        key = (msg.task_id, msg.role)
        q = self._queues.setdefault(key, deque())
        q.append(msg)
        return len(q)

    def pop(self, task_id: str, role: RoleName) -> Optional[ConverseMessage]:
        key = (task_id, role)
        q = self._queues.get(key)
        if not q:
            return None
        return q.popleft()

    def depth(self, task_id: str, role: RoleName) -> int:
        key = (task_id, role)
        return len(self._queues.get(key, []))

    def has_pending(self, task_id: str) -> bool:
        for (tid, _role), q in self._queues.items():
            if tid == task_id and q:
                return True
        return False

    def all_pending(self, task_id: str) -> list[ConverseMessage]:
        out: list[ConverseMessage] = []
        for (tid, _role), q in self._queues.items():
            if tid == task_id:
                out.extend(q)
        return out
