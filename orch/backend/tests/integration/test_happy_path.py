"""End-to-end happy path using MockAdapter (no subprocess, no network)."""

from __future__ import annotations

from pathlib import Path

import pytest

from orch_backend.adapters import AdapterRegistry, MockAdapter
from orch_backend.dispatch import DispatchLoop, RoleRegistry
from orch_backend.domain import (
    PatchProposalExecutor,
    PromptComposer,
    ReqWatcher,
)
from orch_backend.models import TaskStage, TurnPhase
from orch_backend.repo import RepoManager, TaskRegistry
from orch_backend.store import NodeGraphStore


@pytest.fixture()
def orch(tmp_path: Path):
    store = NodeGraphStore(tmp_path / "t.db")
    reg = AdapterRegistry()
    adapter = MockAdapter()
    reg.register("trae", adapter)
    reg.register("mock", MockAdapter())

    rm = RepoManager(tmp_path / "ws")
    tr = TaskRegistry(store, rm)
    role_reg = RoleRegistry(reg)
    composer = PromptComposer(store, history_k=5)
    executor = PatchProposalExecutor(store, clone_repo=rm.clone_repo)
    watcher = ReqWatcher(store)
    loop = DispatchLoop(store, role_reg, composer, executor, watcher)

    yield {
        "store": store, "adapter": adapter, "task_registry": tr,
        "role_registry": role_reg, "dispatch": loop, "executor": executor,
        "composer": composer, "repo_manager": rm,
    }
    store.close()


async def test_happy_path_req_battle_converges_and_builds_tree(orch):
    store = orch["store"]
    dispatch = orch["dispatch"]
    adapter = orch["adapter"]
    tr = orch["task_registry"]

    task = tr.create_task(title="make X", root_requirement="please build X")

    # Round 1: proposer outputs a patch adding REQ nodes; critic approves.
    proposer_text = """I'll decompose into two REQs.

<proposed_patch>
- op: add_node
  kind: REQ
  title: "Login flow"
  description: "user can login"
- op: add_node
  kind: REQ
  title: "Dashboard"
  description: "shows data"
</proposed_patch>

[CONVERGED]
"""
    adapter.set_scripted([proposer_text, "looks good [CONVERGED]"])

    outcome = await dispatch.run_battle(
        task, "req_decomposer", "req_completeness_critic",
        "decompose root into REQs", phase=TurnPhase.REQ_DESIGN,
    )
    assert outcome.converged and outcome.rounds == 1
    nodes = store.list_nodes(task.id)
    assert len(nodes) == 2


async def test_arch_designer_can_declare_add_repo(orch):
    """add_repo op during arch battle clones a local bare upstream."""
    import subprocess
    import asyncio

    store = orch["store"]
    adapter = orch["adapter"]
    dispatch = orch["dispatch"]
    tr = orch["task_registry"]

    # --- make an upstream bare-ish repo ---
    up = Path(store._db_path).parent / "upstream"  # type: ignore[attr-defined]
    up.mkdir()
    subprocess.run(["git", "init", "-b", "master", str(up)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(up), "config", "user.email", "u@x"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(up), "config", "user.name", "u"], check=True, capture_output=True)
    (up / "README").write_text("x")
    subprocess.run(["git", "-C", str(up), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(up), "commit", "-m", "init"], check=True, capture_output=True)

    task = tr.create_task(title="t", root_requirement="x")
    store.set_task_stage(task.id, TaskStage.ARCH_BATTLE_RUNNING)

    arch_text = f"""Need a repo.

<proposed_patch>
- op: add_repo
  git_url: "{up}"
  name: login
  base_branch: master
</proposed_patch>

[CONVERGED]
"""
    adapter.set_scripted([arch_text, "ok [CONVERGED]"])

    outcome = await dispatch.run_battle(
        task, "arch_designer", "arch_coverage_critic",
        "build ARCH", phase=TurnPhase.ARCH_DESIGN,
    )
    assert outcome.converged
    repos = store.list_repos(task.id)
    assert len(repos) == 1 and repos[0].name == "login"
    assert repos[0].init_commit_hash != ""


async def test_converse_triggers_patch_via_dispatch(orch):
    """User message → adapter responds with patch → nodes created."""
    store = orch["store"]
    dispatch = orch["dispatch"]
    adapter = orch["adapter"]
    tr = orch["task_registry"]

    task = tr.create_task(title="t", root_requirement="x")

    adapter.set_scripted(
        [
            "<proposed_patch>\n- op: add_node\n  kind: REQ\n  title: from-converse\n</proposed_patch>\n[CONVERGED]",
            "approved [CONVERGED]",
        ]
    )
    await dispatch.run_battle(
        task, "req_decomposer", "req_completeness_critic",
        "user just said: 我要补充一个 login 需求",
        phase=TurnPhase.CONVERSE,
    )
    nodes = store.list_nodes(task.id)
    assert any(n.title == "from-converse" for n in nodes)


async def test_gate2_req_edit_bounces_to_arch_battle_via_watcher(orch):
    """REQ mutation under GATE2_WAITING causes watcher to revert to ARCH_BATTLE_RUNNING."""
    store = orch["store"]
    dispatch = orch["dispatch"]
    adapter = orch["adapter"]
    tr = orch["task_registry"]

    task = tr.create_task(title="t", root_requirement="x")
    # seed a REQ, put task at GATE2
    from orch_backend.models import Node, NodeKind
    store.add_node(Node(id="req_seed", task_id=task.id, kind=NodeKind.REQ, title="seed"))
    store.set_task_stage(task.id, TaskStage.GATE2_WAITING)

    adapter.set_scripted(
        [
            "<proposed_patch>\n- op: modify_node\n  node_id: req_seed\n  fields: { title: changed }\n</proposed_patch>\n[CONVERGED]",
            "ok [CONVERGED]",
        ]
    )
    await dispatch.run_battle(
        task, "req_decomposer", "req_completeness_critic",
        "补需求", phase=TurnPhase.CONVERSE,
    )
    task_after = store.get_task(task.id)
    assert task_after.stage == TaskStage.ARCH_BATTLE_RUNNING


async def test_ppe_lane_env_var_forwarded_to_adapter(orch):
    """Creating task with ppe_lane causes RoleSession.env.PPE_LANE=<value>."""
    adapter = orch["adapter"]
    tr = orch["task_registry"]
    role_registry = orch["role_registry"]

    task = tr.create_task(title="t", root_requirement="x", ppe_lane="gray-42")
    adapter.set_scripted(["hi"])
    sess = await role_registry.get_or_create_session(task, "arch_designer", "sys")
    assert sess.env == {"PPE_LANE": "gray-42"}


async def test_two_tasks_isolation_no_cross_leak(orch):
    store = orch["store"]
    tr = orch["task_registry"]
    adapter = orch["adapter"]
    dispatch = orch["dispatch"]

    t1 = tr.create_task(title="t1", root_requirement="a")
    t2 = tr.create_task(title="t2", root_requirement="b")

    # run a battle in t1 only
    adapter.set_scripted(
        [
            "<proposed_patch>\n- op: add_node\n  kind: REQ\n  title: in-t1\n</proposed_patch>\n[CONVERGED]",
            "ok [CONVERGED]",
        ]
    )
    await dispatch.run_battle(
        t1, "req_decomposer", "req_completeness_critic",
        "go", phase=TurnPhase.REQ_DESIGN,
    )
    assert len(store.list_nodes(t1.id)) == 1
    assert len(store.list_nodes(t2.id)) == 0
