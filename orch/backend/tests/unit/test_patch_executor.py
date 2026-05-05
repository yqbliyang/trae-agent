"""PatchProposalExecutor — parsing + applying + permissions + rollback."""

from __future__ import annotations

import pytest

from orch_backend.domain import (
    AddEdgeOp,
    AddNodeOp,
    AddRepoOp,
    DeleteNodeOp,
    ModifyNodeOp,
    PatchProposalExecutor,
    PatchValidationError,
    RemoveEdgeOp,
    parse_proposed_patch,
)
from orch_backend.models import EdgeKind, NodeKind


# ---------- parsing ----------

def test_parse_no_patch_block_returns_empty():
    assert parse_proposed_patch("hello world") == []


def test_parse_empty_patch_block_returns_empty():
    assert parse_proposed_patch("<proposed_patch></proposed_patch>") == []


def test_parse_add_node_op():
    text = """
talking... 
<proposed_patch>
- op: add_node
  kind: REQ
  title: "login screen"
  description: "login flow"
  hints:
    - { category: background, weight: must, content: "see repo:login/src/auth.py" }
</proposed_patch>
    """
    ops = parse_proposed_patch(text)
    assert len(ops) == 1 and isinstance(ops[0], AddNodeOp)
    assert ops[0].kind == NodeKind.REQ
    assert ops[0].hints[0].category == "background"


def test_parse_add_repo_op():
    text = """
<proposed_patch>
- op: add_repo
  git_url: https://example.com/login.git
  name: login
  base_branch: master
</proposed_patch>
"""
    ops = parse_proposed_patch(text)
    assert isinstance(ops[0], AddRepoOp) and ops[0].name == "login"


def test_parse_unknown_op_raises():
    with pytest.raises(PatchValidationError):
        parse_proposed_patch("<proposed_patch>\n- op: delete_universe\n  node_id: x\n</proposed_patch>")


def test_parse_malformed_yaml_raises():
    with pytest.raises(PatchValidationError):
        parse_proposed_patch("<proposed_patch>\n- op: add_node\n   kind: [broken\n</proposed_patch>")


# ---------- applying ----------

async def test_apply_add_node_success(store, task_factory):
    t = task_factory()
    ex = PatchProposalExecutor(store)
    ops = [AddNodeOp(kind=NodeKind.REQ, title="a", description="d")]
    summary = await ex.apply(t.id, "req_decomposer", ops)
    assert len(summary.added_nodes) == 1
    assert len(store.list_nodes(t.id)) == 1


async def test_apply_add_node_with_parent_edge(store, task_factory, node_factory):
    t = task_factory()
    root = node_factory(t.id, NodeKind.REQ, id="req_root")
    ex = PatchProposalExecutor(store)
    ops = [AddNodeOp(kind=NodeKind.REQ, title="child", parent_id=root.id)]
    await ex.apply(t.id, "req_decomposer", ops)
    edges = store.list_edges(t.id)
    assert any(e.from_id == root.id and e.kind == EdgeKind.PARENT_OF for e in edges)


async def test_apply_modify_node_forbids_done(store, task_factory, node_factory):
    from orch_backend.models import NodeStatus
    t = task_factory()
    n = node_factory(t.id, NodeKind.REQ, status=NodeStatus.DONE)
    ex = PatchProposalExecutor(store)
    with pytest.raises(PatchValidationError, match="done"):
        await ex.apply(t.id, "arch_designer", [ModifyNodeOp(node_id=n.id, fields={"title": "x"})])


async def test_apply_delete_node_only_pending(store, task_factory, node_factory):
    from orch_backend.models import NodeStatus
    t = task_factory()
    n = node_factory(t.id, NodeKind.REQ, status=NodeStatus.RUNNING)
    ex = PatchProposalExecutor(store)
    with pytest.raises(PatchValidationError):
        await ex.apply(t.id, "arch_designer", [DeleteNodeOp(node_id=n.id)])


async def test_apply_rollback_on_failure(store, task_factory):
    """If the second op fails, the first op must roll back."""
    t = task_factory()
    ex = PatchProposalExecutor(store)
    ops = [
        AddNodeOp(kind=NodeKind.REQ, title="good"),
        ModifyNodeOp(node_id="nonexistent", fields={"title": "x"}),
    ]
    with pytest.raises(PatchValidationError):
        await ex.apply(t.id, "req_decomposer", ops)
    assert store.list_nodes(t.id) == []


async def test_add_repo_requires_arch_designer(store, task_factory):
    t = task_factory()

    async def clone(*a, **k):
        return {"local_path": "/tmp/login", "base_commit_hash": "abc", "init_commit_hash": "def"}

    ex = PatchProposalExecutor(store, clone_repo=clone)
    op = AddRepoOp(git_url="u", name="login", base_branch="master")
    with pytest.raises(PatchValidationError, match="arch_designer"):
        await ex.apply(t.id, "req_decomposer", [op])
    # permitted for arch_designer
    summary = await ex.apply(t.id, "arch_designer", [op])
    assert summary.added_repos[0]["name"] == "login"
    assert len(store.list_repos(t.id)) == 1


async def test_add_repo_clone_failure_rollback(store, task_factory):
    t = task_factory()

    async def broken_clone(*a, **k):
        raise RuntimeError("boom")

    ex = PatchProposalExecutor(store, clone_repo=broken_clone)
    op = AddRepoOp(git_url="u", name="login", base_branch="master")
    with pytest.raises(PatchValidationError, match="clone_repo failed"):
        await ex.apply(t.id, "arch_designer", [op])
    assert store.list_repos(t.id) == []


async def test_parse_and_apply_end_to_end(store, task_factory):
    t = task_factory()
    text = """
thinking...
<proposed_patch>
- op: add_node
  kind: REQ
  title: root
- op: add_node
  kind: REQ
  title: child
</proposed_patch>
"""
    ex = PatchProposalExecutor(store)
    summary = await ex.apply(t.id, "req_decomposer", parse_proposed_patch(text))
    assert len(summary.added_nodes) == 2
