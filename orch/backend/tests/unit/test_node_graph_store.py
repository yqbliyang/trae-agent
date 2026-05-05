"""NodeGraphStore invariants."""

from __future__ import annotations

import pytest

from orch_backend.models import (
    Edge,
    EdgeKind,
    Node,
    NodeKind,
    NodeStatus,
    Repo,
    TaskStage,
    Turn,
    TurnOrigin,
    TurnPhase,
)
from orch_backend.store import NodeGraphStore, StoreError


def test_add_and_get_node(store, task_factory):
    task = task_factory()
    n = Node(
        id="req_1", task_id=task.id, kind=NodeKind.REQ, title="t"
    )
    store.add_node(n)
    got = store.get_node("req_1")
    assert got is not None and got.title == "t"


def test_list_nodes_scoped_by_task(store, task_factory, node_factory):
    t1 = task_factory(id="task_1")
    t2 = task_factory(id="task_2")
    node_factory(t1.id, NodeKind.REQ)
    node_factory(t1.id, NodeKind.REQ)
    node_factory(t2.id, NodeKind.REQ)
    assert len(store.list_nodes(t1.id)) == 2
    assert len(store.list_nodes(t2.id)) == 1


def test_arch_nesting_forbidden(store, task_factory, node_factory, parent_edge):
    task = task_factory()
    req = node_factory(task.id, NodeKind.REQ, id="req_1")
    arch1 = node_factory(task.id, NodeKind.ARCH, id="arch_1")
    parent_edge(req.id, arch1.id, task.id)

    arch2 = Node(
        id="arch_2", task_id=task.id, kind=NodeKind.ARCH, title="nested"
    )
    store.add_node(arch2)
    parent_edge(arch1.id, arch2.id, task.id)
    with pytest.raises(StoreError, match="ARCH nesting"):
        store.update_node(arch2)


def test_code_parent_must_be_arch(store, task_factory, node_factory, parent_edge):
    task = task_factory()
    req = node_factory(task.id, NodeKind.REQ, id="req_1")
    code = Node(
        id="code_1", task_id=task.id, kind=NodeKind.CODE, title="c"
    )
    store.add_node(code)
    parent_edge(req.id, code.id, task.id)
    with pytest.raises(StoreError, match="parent must be ARCH"):
        store.update_node(code)


def test_delete_node_in_running_status_forbidden(store, task_factory, node_factory):
    task = task_factory()
    n = node_factory(task.id, NodeKind.REQ, status=NodeStatus.RUNNING)
    with pytest.raises(StoreError):
        store.delete_node(n.id)


def test_set_task_stage(store, task_factory):
    t = task_factory()
    store.set_task_stage(t.id, TaskStage.GATE1_WAITING)
    updated = store.get_task(t.id)
    assert updated is not None and updated.stage == TaskStage.GATE1_WAITING


def test_append_and_list_turns_ordered(store, task_factory):
    t = task_factory()
    t1 = Turn(
        id="turn_1",
        task_id=t.id,
        role="req_decomposer",
        phase=TurnPhase.REQ_DESIGN,
        origin=TurnOrigin.BATTLE,
        round_index=1,
        output_text="hello",
    )
    t2 = Turn(
        id="turn_2",
        task_id=t.id,
        role="req_completeness_critic",
        phase=TurnPhase.REQ_DESIGN,
        origin=TurnOrigin.BATTLE,
        round_index=1,
        output_text="ok",
    )
    store.append_turn(t1)
    store.append_turn(t2)
    all_ = store.list_turns(t.id)
    assert [x.id for x in all_] == ["turn_1", "turn_2"]
    only_dec = store.list_turns(t.id, role="req_decomposer")
    assert len(only_dec) == 1


def test_repo_unique_name_per_task(store, task_factory):
    t = task_factory()
    r1 = Repo(
        id="r1", task_id=t.id, name="login", git_url="u", base_branch="master", task_branch="orch/a/x"
    )
    store.add_repo(r1)
    r2 = Repo(
        id="r2", task_id=t.id, name="login", git_url="u2", base_branch="master", task_branch="orch/a/x"
    )
    with pytest.raises(StoreError):
        store.add_repo(r2)


def test_edges_scoped_by_task(store, task_factory, node_factory, parent_edge):
    t = task_factory()
    a = node_factory(t.id, NodeKind.REQ)
    b = node_factory(t.id, NodeKind.REQ)
    parent_edge(a.id, b.id, t.id)
    edges = store.list_edges(t.id)
    assert len(edges) == 1 and edges[0].kind == EdgeKind.PARENT_OF


def test_remove_edge(store, task_factory, node_factory, parent_edge):
    t = task_factory()
    a = node_factory(t.id, NodeKind.REQ)
    b = node_factory(t.id, NodeKind.REQ)
    parent_edge(a.id, b.id, t.id)
    store.remove_edge(a.id, b.id, EdgeKind.PARENT_OF)
    assert store.list_edges(t.id) == []


def test_store_persists_across_reopen(tmp_path, task_factory):
    db = tmp_path / "keep.db"
    s1 = NodeGraphStore(db)
    t = task_factory()  # this uses the fixture-store, not s1
    # switch to a fresh store on the same file path
    s1.close()
    s2 = NodeGraphStore(db)
    # we can't read task_factory's row here because fixture used a different file;
    # instead, directly add and re-open:
    s3 = NodeGraphStore(db)
    from orch_backend.models import Task

    task = Task(
        id="task_keep", title="x", root_requirement="r",
        workspace_path="/w", task_branch="orch/a/b",
    )
    s3.upsert_task(task)
    s3.close()
    s4 = NodeGraphStore(db)
    got = s4.get_task("task_keep")
    assert got is not None
    s4.close()
    s2.close()
