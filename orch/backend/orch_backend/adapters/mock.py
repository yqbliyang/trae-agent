"""MockAdapter — deterministic scripted replies for tests."""

from __future__ import annotations

import uuid
from typing import Callable, Optional

from orch_backend.adapters.base import (
    AdapterError,
    AssistantReply,
    CodingAgentAdapter,
    SessionHandle,
    StreamCallback,
    StreamEvent,
)
from orch_backend.models import AdapterCapabilities


class MockAdapter(CodingAgentAdapter):
    """Scripted or callback-based adapter, used in unit + integration tests."""

    capabilities: AdapterCapabilities = AdapterCapabilities(
        name="mock", supports_session_resume=False, supports_streaming=True
    )

    def __init__(
        self,
        scripted_outputs: Optional[list[str]] = None,
        callback: Optional[Callable[[SessionHandle, str], str]] = None,
    ) -> None:
        self._scripted: list[str] = list(scripted_outputs or [])
        self._callback = callback
        self.sent: list[tuple[str, str, dict[str, str]]] = []  # (role, msg, env)
        self.sessions: dict[str, SessionHandle] = {}

    def set_scripted(self, items: list[str]) -> None:
        self._scripted = list(items)

    def set_next_reply(self, text: str) -> None:
        self._scripted.append(text)

    async def start_session(
        self,
        role_name: str,
        system_prompt: str,
        cwd: str,
        env: Optional[dict[str, str]] = None,
    ) -> SessionHandle:
        sid = uuid.uuid4().hex[:8]
        h = SessionHandle(
            session_id=sid,
            role_name=role_name,
            cwd=cwd,
            env=dict(env or {}),
            state={"system_prompt": system_prompt},
        )
        self.sessions[sid] = h
        return h

    async def send(
        self,
        session: SessionHandle,
        user_message: str,
        stream_cb: Optional[StreamCallback] = None,
    ) -> AssistantReply:
        self.sent.append((session.role_name, user_message, dict(session.env)))

        if self._callback:
            text = self._callback(session, user_message)
        elif self._scripted:
            text = self._scripted.pop(0)
        else:
            raise AdapterError("MockAdapter: no scripted reply available")

        if stream_cb is not None:
            for chunk in _chunk_text(text, n=8):
                await stream_cb(StreamEvent(kind="token", text=chunk))
            await stream_cb(StreamEvent(kind="end"))

        return AssistantReply(text=text, artifacts=[])

    async def end_session(self, session: SessionHandle) -> None:
        self.sessions.pop(session.session_id, None)

    def resolve_artifacts(self, session: SessionHandle) -> list[str]:
        return []


def _chunk_text(text: str, n: int = 8) -> list[str]:
    return [text[i : i + n] for i in range(0, len(text), n)] or [""]
