"""Model-layer invariants."""

from __future__ import annotations

import pytest

from orch_backend.models import (
    DEFAULT_MAX_ROUNDS,
    NodeHint,
    RoleConfig,
    Task,
    TaskStage,
)


def test_default_max_rounds_is_5():
    assert DEFAULT_MAX_ROUNDS == 5


def test_task_model_accepts_minimal_fields():
    t = Task(
        id="task_1",
        title="x",
        root_requirement="r",
        workspace_path="/w",
        task_branch="orch/a/b",
    )
    assert t.ppe_lane is None
    assert t.execution_mode == "inherit"
    assert t.stage == TaskStage.REQ_BATTLE_RUNNING


def test_task_model_rejects_legacy_max_rounds_field():
    with pytest.raises(ValueError):
        Task(
            id="task_1",
            title="x",
            root_requirement="r",
            workspace_path="/w",
            task_branch="orch/a/b",
            max_design_rounds_req=3,  # type: ignore[call-arg]
        )


def test_task_model_rejects_legacy_repos_spec_field():
    with pytest.raises(ValueError):
        Task(
            id="task_1",
            title="x",
            root_requirement="r",
            workspace_path="/w",
            task_branch="orch/a/b",
            repos_spec=[{"git_url": "u"}],  # type: ignore[call-arg]
        )


def test_task_branch_must_be_non_empty_string_when_provided():
    t = Task(
        id="task_1",
        title="x",
        root_requirement="r",
        workspace_path="/w",
        task_branch="orch/a/b",
    )
    assert t.task_branch == "orch/a/b"


def test_task_ppe_lane_optional():
    t = Task(
        id="task_1",
        title="x",
        root_requirement="r",
        workspace_path="/w",
        task_branch="orch/a/b",
        ppe_lane="gray-1",
    )
    assert t.ppe_lane == "gray-1"


def test_node_hint_weights_enum_like():
    h = NodeHint(category="background", content="ctx", weight="must")
    assert h.weight == "must"
    with pytest.raises(ValueError):
        NodeHint(category="c", content="x", weight="maybe")  # type: ignore[arg-type]


def test_role_config_default_adapter_is_trae():
    r = RoleConfig()
    assert r.adapter == "trae"
    assert r.trae_config_path is None
