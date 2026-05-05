"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

from orch_backend.models import (
    Edge,
    EdgeKind,
    Node,
    NodeKind,
    NodeStatus,
    Task,
    TaskStage,
)
from orch_backend.store import NodeGraphStore


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[NodeGraphStore]:
    s = NodeGraphStore(tmp_path / "test.db")
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def task_factory(store: NodeGraphStore):
    def _make(**kwargs) -> Task:
        payload = dict(
            id=kwargs.get("id", NodeGraphStore.new_id("task_")),
            title=kwargs.get("title", "t"),
            root_requirement=kwargs.get("root_requirement", "r"),
            workspace_path=kwargs.get("workspace_path", "/tmp/ws"),
            task_branch=kwargs.get("task_branch", "orch/abc/x"),
            ppe_lane=kwargs.get("ppe_lane"),
            stage=kwargs.get("stage", TaskStage.REQ_BATTLE_RUNNING),
        )
        task = Task(**payload)
        store.upsert_task(task)
        return task

    return _make


@pytest.fixture()
def node_factory(store: NodeGraphStore):
    def _make(task_id: str, kind: NodeKind, **kwargs) -> Node:
        node = Node(
            id=kwargs.get("id", NodeGraphStore.new_id(f"{kind.value.lower()}_")),
            task_id=task_id,
            kind=kind,
            title=kwargs.get("title", f"{kind.value} n"),
            description=kwargs.get("description", ""),
            status=kwargs.get("status", NodeStatus.PENDING),
            hints=kwargs.get("hints", []),
            design_content=kwargs.get("design_content", ""),
        )
        store.add_node(node)
        return node

    return _make


@pytest.fixture()
def parent_edge(store: NodeGraphStore):
    def _make(from_id: str, to_id: str, task_id: str, kind: EdgeKind = EdgeKind.PARENT_OF) -> Edge:
        edge = Edge(
            id=NodeGraphStore.new_id("edge_"),
            task_id=task_id,
            from_id=from_id,
            to_id=to_id,
            kind=kind,
        )
        store.add_edge(edge)
        return edge

    return _make
