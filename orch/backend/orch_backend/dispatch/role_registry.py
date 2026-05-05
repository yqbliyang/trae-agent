"""RoleRegistry — binds roles to adapters and lazily opens sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from orch_backend.adapters import AdapterRegistry, CodingAgentAdapter, SessionHandle
from orch_backend.models import RoleConfig, RoleName, Task


@dataclass
class RoleSession:
    """Bundles adapter + SessionHandle for a (task, role) pair."""

    role_name: RoleName
    adapter_name: str
    adapter: CodingAgentAdapter
    handle: SessionHandle
    env: dict[str, str] = field(default_factory=dict)


class RoleRegistry:
    """Holds (task_id, role_name) → RoleSession; creates on demand."""

    def __init__(self, adapter_registry: AdapterRegistry) -> None:
        self._adapters = adapter_registry
        self._sessions: dict[tuple[str, str], RoleSession] = {}

    def resolve_adapter(self, task: Task, role: RoleName) -> str:
        """Resolve which adapter a role should use (override > default 'trae')."""
        override = task.role_config_override.get(role)
        if override:
            return override.adapter
        return "trae"

    async def get_or_create_session(
        self,
        task: Task,
        role: RoleName,
        system_prompt: str,
    ) -> RoleSession:
        key = (task.id, role)
        if key in self._sessions:
            return self._sessions[key]

        adapter_name = self.resolve_adapter(task, role)
        adapter = self._adapters.get(adapter_name)
        env: dict[str, str] = {}
        if task.ppe_lane:
            env["PPE_LANE"] = task.ppe_lane
        ov = task.role_config_override.get(role)
        if ov is not None and ov.trae_config_path:
            env["ORCH_TRAE_CONFIG_PATH"] = ov.trae_config_path
        handle = await adapter.start_session(
            role_name=role,
            system_prompt=system_prompt,
            cwd=task.workspace_path,
            env=env,
        )
        sess = RoleSession(
            role_name=role,
            adapter_name=adapter_name,
            adapter=adapter,
            handle=handle,
            env=env,
        )
        self._sessions[key] = sess
        return sess

    def session_count(self) -> int:
        return len(self._sessions)

    async def end_task_sessions(self, task_id: str) -> None:
        keys = [k for k in self._sessions if k[0] == task_id]
        for k in keys:
            sess = self._sessions.pop(k)
            try:
                await sess.adapter.end_session(sess.handle)
            except Exception:  # pragma: no cover
                pass
