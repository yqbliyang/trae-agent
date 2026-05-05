"""ConverseQueue + ReqWatcher + PromptComposer."""

from __future__ import annotations

from orch_backend.domain import (
    AppliedPatchSummary,
    ConverseMessage,
    ConverseQueue,
    PromptComposer,
    ReqWatcher,
)
from orch_backend.models import NodeKind, TaskStage


def test_converse_queue_fifo_per_role():
    q = ConverseQueue()
    q.enqueue(ConverseMessage(id="m1", task_id="t", role="arch_designer", message="a"))
    q.enqueue(ConverseMessage(id="m2", task_id="t", role="arch_designer", message="b"))
    q.enqueue(ConverseMessage(id="m3", task_id="t", role="req_decomposer", message="c"))
    assert q.depth("t", "arch_designer") == 2
    assert q.pop("t", "arch_designer").id == "m1"
    assert q.pop("t", "arch_designer").id == "m2"
    assert q.pop("t", "req_decomposer").id == "m3"
    assert q.pop("t", "arch_designer") is None


def test_converse_queue_has_pending():
    q = ConverseQueue()
    assert q.has_pending("t") is False
    q.enqueue(ConverseMessage(id="m1", task_id="t", role="arch_designer", message="x"))
    assert q.has_pending("t") is True


def test_req_watcher_reverts_to_arch_battle_on_req_change(store, task_factory, node_factory):
    task = task_factory(stage=TaskStage.GATE2_WAITING)
    store.set_task_stage(task.id, TaskStage.GATE2_WAITING)
    req = node_factory(task.id, NodeKind.REQ)
    calls = []

    w = ReqWatcher(store, on_rewind=lambda tid: calls.append(tid))
    summary = AppliedPatchSummary(modified_nodes=[req.id])
    assert w.notify(task.id, summary) is True
    updated = store.get_task(task.id)
    assert updated is not None and updated.stage == TaskStage.ARCH_BATTLE_RUNNING
    assert calls == [task.id]


def test_req_watcher_does_not_fire_outside_gate2(store, task_factory, node_factory):
    task = task_factory()  # default REQ_BATTLE_RUNNING
    req = node_factory(task.id, NodeKind.REQ)
    w = ReqWatcher(store)
    assert w.notify(task.id, AppliedPatchSummary(modified_nodes=[req.id])) is False


def test_req_watcher_ignores_non_req_changes(store, task_factory, node_factory, parent_edge):
    task = task_factory(stage=TaskStage.GATE2_WAITING)
    store.set_task_stage(task.id, TaskStage.GATE2_WAITING)
    req = node_factory(task.id, NodeKind.REQ)
    arch = node_factory(task.id, NodeKind.ARCH)
    parent_edge(req.id, arch.id, task.id)

    w = ReqWatcher(store)
    summary = AppliedPatchSummary(modified_nodes=[arch.id])
    assert w.notify(task.id, summary) is False


def test_prompt_composer_injects_recent_turns(store, task_factory):
    task = task_factory()
    from orch_backend.models import Turn, TurnOrigin, TurnPhase
    for i in range(7):
        store.append_turn(
            Turn(
                id=f"tt_{i}",
                task_id=task.id,
                role="req_decomposer",
                phase=TurnPhase.REQ_DESIGN,
                origin=TurnOrigin.BATTLE,
                round_index=i,
                output_text=f"round-{i}",
            )
        )
    pc = PromptComposer(store, history_k=3)
    body = pc.compose_for_role(task, "req_decomposer", "keep going")
    assert "round-4" in body and "round-5" in body and "round-6" in body
    assert "round-0" not in body


def test_prompt_composer_includes_task_branch_and_ppe_lane(store, task_factory):
    task = task_factory(ppe_lane="gray-1", task_branch="orch/x/test")
    pc = PromptComposer(store)
    body = pc.compose_for_role(task, "arch_designer", "go")
    assert "orch/x/test" in body and "gray-1" in body


def test_prompt_composer_system_prompt_mentions_playwright_and_patch_xml(store):
    pc = PromptComposer(store)
    sys = pc.system_prompt_for("arch_designer")
    assert "Playwright" in sys or "playwright" in sys
    assert "<proposed_patch>" in sys


def test_prompt_composer_all_4_roles_have_system_prompts(store):
    pc = PromptComposer(store)
    for r in ("req_decomposer", "req_completeness_critic", "arch_designer", "arch_coverage_critic"):
        txt = pc.system_prompt_for(r)  # type: ignore[arg-type]
        assert "你的角色" in txt
