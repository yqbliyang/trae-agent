"""Unit tests for ConverseRunner."""

from __future__ import annotations

import pytest

from orch_backend.adapters import AdapterRegistry, MockAdapter
from orch_backend.api.converse_runner import ConverseRunner
from orch_backend.dispatch import RoleRegistry
from orch_backend.domain import (
    ConverseMessage,
    ConverseQueue,
    PatchProposalExecutor,
    PromptComposer,
    ReqWatcher,
)
from orch_backend.event_bus import EventBus
from orch_backend.models import TurnPhase
from orch_backend.repo import RepoManager, TaskRegistry


@pytest.fixture()
def cr_ctx(tmp_path):
    from orch_backend.store import NodeGraphStore

    store = NodeGraphStore(tmp_path / "db.sqlite")
    queue = ConverseQueue()
    reg = AdapterRegistry()
    adapter = MockAdapter(
        scripted_outputs=["<proposed_patch>\n- op: add_node\n  kind: REQ\n  title: c1\n</proposed_patch>\n"]
    )
    reg.register("mock", adapter)
    reg.register("trae", adapter)
    rr = RoleRegistry(reg)
    composer = PromptComposer(store)
    patches = PatchProposalExecutor(store, clone_repo=None)
    ev = EventBus()
    runner = ConverseRunner(
        store=store,
        queue=queue,
        role_registry=rr,
        composer=composer,
        patches=patches,
        req_watcher=ReqWatcher(store),
        event_bus=ev,
    )
    return store, queue, runner, adapter


@pytest.mark.asyncio
async def test_converse_runner_applies_patch(cr_ctx, tmp_path):
    store, queue, runner, _adapter = cr_ctx
    rm = RepoManager(tmp_path / "ws2")
    tr = TaskRegistry(store, rm)
    task = tr.create_task(title="x", root_requirement="y")
    queue.enqueue(
        ConverseMessage(
            id="m1",
            task_id=task.id,
            role="req_decomposer",
            message="add node",
            referenced_node_ids=[],
        )
    )
    t = await runner.process_one(task.id, "req_decomposer")
    assert t is not None
    assert len(store.list_nodes(task.id)) == 1
    conv = [
        x
        for x in store.list_turns(task.id)
        if x.role == "req_decomposer" and x.phase == TurnPhase.CONVERSE
    ]
    assert len(conv) >= 1


@pytest.mark.asyncio
async def test_converse_runner_empty_queue_returns_none(cr_ctx):
    store, queue, runner, _adapter = cr_ctx
    assert await runner.process_one("no_such", "arch_designer") is None
