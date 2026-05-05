"""Core Pydantic models (plan §3)."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_MAX_ROUNDS: int = 5


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class NodeKind(str, Enum):
    REQ = "REQ"
    ARCH = "ARCH"
    CODE = "CODE"
    TEST = "TEST"


class NodeStatus(str, Enum):
    PENDING = "pending"
    DESIGN_PENDING = "design_pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    DEPRECATED = "deprecated"


class EdgeKind(str, Enum):
    PARENT_OF = "parent_of"
    HAS_CODE_CHILD = "has_code_child"
    HAS_TEST_CHILD = "has_test_child"
    SATISFIES = "satisfies"
    COVERS = "covers"
    DEPENDS_ON = "depends_on"
    VALIDATES = "validates"


RoleName = Literal[
    "req_decomposer",
    "req_completeness_critic",
    "arch_designer",
    "arch_coverage_critic",
    "human",
    "system",
]


class TaskStage(str, Enum):
    REQ_BATTLE_RUNNING = "req_battle_running"
    GATE1_WAITING = "gate1_waiting"
    ARCH_BATTLE_RUNNING = "arch_battle_running"
    GATE2_WAITING = "gate2_waiting"
    EXECUTING = "executing"
    DONE = "done"
    FAILED = "failed"
    ARCHIVED = "archived"


class HitlGate(str, Enum):
    GATE1 = "gate1"
    GATE2 = "gate2"
    NODE_FAILURE = "node_failure"
    DESIGN_CHANGE = "design_change"


class HitlAction(str, Enum):
    APPROVE = "approve"
    REJECT_WITH_COMMENT = "reject_with_comment"
    APPROVE_PARTIAL = "approve_partial"
    CONTINUE_BATTLE = "continue_battle"


class TurnPhase(str, Enum):
    REQ_DESIGN = "req_design"
    ARCH_DESIGN = "arch_design"
    EXECUTION = "execution"
    CONVERSE = "converse"
    HITL = "hitl"
    SYSTEM = "system"


class TurnOrigin(str, Enum):
    USER = "user"
    BATTLE = "battle"
    CONVERSE = "converse"
    IMPL = "impl"
    SYSTEM = "system"


class NodeHint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    content: str
    weight: Literal["must", "should", "nice"] = "should"


class Node(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    task_id: str
    kind: NodeKind
    title: str
    description: str = ""
    status: NodeStatus = NodeStatus.PENDING
    hints: list[NodeHint] = Field(default_factory=list)
    design_content: str = ""
    managed_code_nodes: list[str] = Field(default_factory=list)
    managed_test_nodes: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now_utc)
    updated_at: datetime = Field(default_factory=_now_utc)


class Edge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    task_id: str
    from_id: str
    to_id: str
    kind: EdgeKind
    created_at: datetime = Field(default_factory=_now_utc)


class Repo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    task_id: str
    name: str
    git_url: str
    base_branch: str
    task_branch: str
    base_commit_hash: str = ""
    init_commit_hash: str = ""
    local_path: str = ""
    created_at: datetime = Field(default_factory=_now_utc)


class AdapterCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    supports_session_resume: bool = False
    supports_streaming: bool = True
    notes: str = ""


class RoleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adapter: str = "trae"
    trae_config_path: Optional[str] = None
    extra: dict[str, Any] = Field(default_factory=dict)


class Task(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    root_requirement: str
    workspace_path: str
    task_branch: str
    ppe_lane: Optional[str] = None
    stage: TaskStage = TaskStage.REQ_BATTLE_RUNNING
    execution_mode: Literal["inherit"] = "inherit"
    role_config_override: dict[str, RoleConfig] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now_utc)
    updated_at: datetime = Field(default_factory=_now_utc)


class Turn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    task_id: str
    role: RoleName
    adapter_name: str = "mock"
    phase: TurnPhase
    origin: TurnOrigin
    round_index: int = 0
    input_text: str = ""
    output_text: str = ""
    consumed_artifacts: list[str] = Field(default_factory=list)
    produced_artifacts: list[str] = Field(default_factory=list)
    payload_extra: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now_utc)


class HitlDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    task_id: str
    gate: HitlGate
    action: HitlAction
    comment: str = ""
    per_node_decisions: dict[str, dict[str, str]] = Field(default_factory=dict)
    continue_extra_rounds: Optional[int] = None
    created_at: datetime = Field(default_factory=_now_utc)


class DesignChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    task_id: str
    requested_by_role: RoleName
    rationale: str
    proposed_patch_preview: str = ""
    status: Literal["pending", "approved", "rejected"] = "pending"
    created_at: datetime = Field(default_factory=_now_utc)


class NodeFailureEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    task_id: str
    node_id: str
    reason: str
    created_at: datetime = Field(default_factory=_now_utc)
