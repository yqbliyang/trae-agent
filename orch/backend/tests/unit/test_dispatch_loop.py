"""DispatchLoop battle + converge detection."""

from __future__ import annotations

import pytest

from orch_backend.adapters import AdapterRegistry, MockAdapter
from orch_backend.dispatch import DispatchLoop, RoleRegistry
from orch_backend.domain import PatchProposalExecutor, PromptComposer, ReqWatcher
from orch_backend.models import TurnPhase


@pytest.fixture()
def dispatch(store, task_factory):
    t = task_factory()
    reg = AdapterRegistry()
    adapter = MockAdapter()
    reg.register("trae", adapter)
    role_reg = RoleRegistry(reg)
    composer = PromptComposer(store, history_k=3)
    executor = PatchProposalExecutor(store)
    watcher = ReqWatcher(store)
    loop = DispatchLoop(store, role_reg, composer, executor, watcher)
    return loop, adapter, t


async def test_battle_converges_explicit_marker(dispatch):
    loop, adapter, t = dispatch
    adapter.set_scripted(
        [
            "proposer r1",
            "critic r1 [CONVERGED]",
        ]
    )
    outcome = await loop.run_battle(
        t, "req_decomposer", "req_completeness_critic",
        "请拆分 REQ", phase=TurnPhase.REQ_DESIGN,
    )
    assert outcome.converged and outcome.reason == "explicit"
    assert outcome.rounds == 1


async def test_battle_converges_implicit_identical_two(dispatch):
    loop, adapter, t = dispatch
    # round 1: proposer, critic. round 2: proposer, critic identical to round 1.
    adapter.set_scripted(
        [
            "p-1",
            "c-1-same",
            "p-2",
            "c-1-same",
        ]
    )
    outcome = await loop.run_battle(
        t, "req_decomposer", "req_completeness_critic",
        "go", phase=TurnPhase.REQ_DESIGN,
    )
    assert outcome.converged and outcome.reason == "implicit"
    assert outcome.rounds == 2


async def test_battle_max_rounds_without_convergence(dispatch):
    loop, adapter, t = dispatch
    # 5 rounds = 10 replies, all unique. Critic never says [CONVERGED].
    adapter.set_scripted(
        [f"p-{i}" for i in range(5)]
        + [f"c-{i}" for i in range(5)]
    )
    # interleave: each round uses 2
    adapter.set_scripted(
        [
            "p-1", "c-1",
            "p-2", "c-2",
            "p-3", "c-3",
            "p-4", "c-4",
            "p-5", "c-5",
        ]
    )
    outcome = await loop.run_battle(
        t, "req_decomposer", "req_completeness_critic",
        "go", phase=TurnPhase.REQ_DESIGN,
        max_rounds=5,
    )
    assert not outcome.converged
    assert outcome.reason == "max_rounds"
    assert outcome.rounds == 5


async def test_battle_applies_patch_from_proposer(dispatch, store):
    loop, adapter, t = dispatch
    patch_text = """thinking...
<proposed_patch>
- op: add_node
  kind: REQ
  title: parent
</proposed_patch>
"""
    adapter.set_scripted([patch_text, "critic [CONVERGED]"])
    outcome = await loop.run_battle(
        t, "req_decomposer", "req_completeness_critic",
        "go", phase=TurnPhase.REQ_DESIGN,
    )
    assert outcome.converged
    assert len(store.list_nodes(t.id)) == 1


async def test_battle_records_validation_error_turn_on_bad_patch(dispatch, store):
    loop, adapter, t = dispatch
    bad_patch = """
<proposed_patch>
- op: modify_node
  node_id: does-not-exist
  fields: { title: "x" }
</proposed_patch>
"""
    adapter.set_scripted([bad_patch, "critic [CONVERGED]"])
    await loop.run_battle(
        t, "req_decomposer", "req_completeness_critic",
        "go", phase=TurnPhase.REQ_DESIGN,
    )
    turns = store.list_turns(t.id)
    # one system turn with validation error marker
    assert any(
        x.role == "system" and "[VALIDATION_ERROR]" in x.output_text for x in turns
    )


async def test_battle_persists_turns_in_order(dispatch, store):
    loop, adapter, t = dispatch
    adapter.set_scripted(["p1", "c1 [CONVERGED]"])
    await loop.run_battle(
        t, "arch_designer", "arch_coverage_critic",
        "do", phase=TurnPhase.ARCH_DESIGN,
    )
    turns = [x for x in store.list_turns(t.id) if x.role != "system"]
    assert [x.role for x in turns] == ["arch_designer", "arch_coverage_critic"]


async def test_role_registry_resolves_default_adapter_trae(dispatch, task_factory):
    loop, _, _ = dispatch
    # default no override → trae
    task = task_factory()
    assert loop.roles.resolve_adapter(task, "arch_designer") == "trae"


async def test_role_registry_passes_ppe_lane_env(store, task_factory):
    task = task_factory(ppe_lane="gray-7")
    reg = AdapterRegistry()
    adapter = MockAdapter(scripted_outputs=["hi"])
    reg.register("trae", adapter)
    rr = RoleRegistry(reg)
    sess = await rr.get_or_create_session(task, "arch_designer", "sys")
    assert sess.env == {"PPE_LANE": "gray-7"}
    assert sess.handle.env == {"PPE_LANE": "gray-7"}
