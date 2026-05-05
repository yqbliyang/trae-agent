"""CodingAgentAdapter protocol + built-in adapters."""

from orch_backend.adapters.base import (
    AdapterError,
    AssistantReply,
    CodingAgentAdapter,
    SessionHandle,
    StreamCallback,
    StreamEvent,
)
from orch_backend.adapters.mock import MockAdapter
from orch_backend.adapters.registry import AdapterRegistry
from orch_backend.adapters.trae import (
    DEFAULT_SHIPPED_CONFIG,
    TraeAgentAdapter,
    _ensure_playwright_profile,
    is_profile_bootstrap_needed,
    resolve_trae_cli_executable,
)

__all__ = [
    "AdapterError",
    "AdapterRegistry",
    "AssistantReply",
    "CodingAgentAdapter",
    "DEFAULT_SHIPPED_CONFIG",
    "MockAdapter",
    "SessionHandle",
    "StreamCallback",
    "StreamEvent",
    "TraeAgentAdapter",
    "resolve_trae_cli_executable",
    "_ensure_playwright_profile",
    "is_profile_bootstrap_needed",
]
