"""Protocol for coding/analysis agents used by the orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional, Protocol, runtime_checkable

from orch_backend.models import AdapterCapabilities


class AdapterError(Exception):
    """Adapter-side failure (subprocess crash, timeout, malformed output, etc.)."""


@dataclass
class StreamEvent:
    kind: str  # "token" | "tool_call" | "tool_result" | "end"
    text: str = ""
    data: dict = field(default_factory=dict)


StreamCallback = Callable[[StreamEvent], Awaitable[None]]


@dataclass
class SessionHandle:
    session_id: str
    role_name: str
    cwd: str
    env: dict[str, str] = field(default_factory=dict)
    state: dict = field(default_factory=dict)


@dataclass
class AssistantReply:
    text: str
    artifacts: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)


@runtime_checkable
class CodingAgentAdapter(Protocol):
    """All coding agents plug through this 5-method contract."""

    capabilities: AdapterCapabilities

    async def start_session(
        self,
        role_name: str,
        system_prompt: str,
        cwd: str,
        env: Optional[dict[str, str]] = None,
    ) -> SessionHandle: ...

    async def send(
        self,
        session: SessionHandle,
        user_message: str,
        stream_cb: Optional[StreamCallback] = None,
    ) -> AssistantReply: ...

    async def end_session(self, session: SessionHandle) -> None: ...

    def resolve_artifacts(self, session: SessionHandle) -> list[str]: ...
