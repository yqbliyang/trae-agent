"""Dispatch + role registries."""

from orch_backend.dispatch.dispatch_loop import (
    DEFAULT_MAX_ROUNDS,
    BattleOutcome,
    DispatchLoop,
)
from orch_backend.dispatch.role_registry import RoleRegistry, RoleSession

__all__ = [
    "BattleOutcome",
    "DEFAULT_MAX_ROUNDS",
    "DispatchLoop",
    "RoleRegistry",
    "RoleSession",
]
