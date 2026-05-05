"""PatchProposalExecutor — parses `<proposed_patch>` and applies atomically.

Grammar (plan A.0):

    <proposed_patch>
      - op: add_node
        parent_id: <id>
        kind: REQ|ARCH|CODE|TEST
        title: ...
        description: ...
        hints:
          - { category: ..., weight: must|should|nice, content: ... }
      - op: modify_node
        node_id: <id>
        fields:
          title: ...
          description: ...
          hints_append: [...]
          design_content_append: ...
          status: deprecated
      - op: delete_node
        node_id: <id>
      - op: add_edge
        from: <id>
        to: <id>
        kind: satisfies|covers|depends_on
      - op: remove_edge
        from: <id>
        to: <id>
        kind: ...
      - op: add_repo         # only arch_designer
        git_url: ...
        name: ...
        base_branch: ...
    </proposed_patch>
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional, Union

import yaml

from orch_backend.models import (
    Edge,
    EdgeKind,
    Node,
    NodeHint,
    NodeKind,
    NodeStatus,
    Repo,
    RoleName,
)
from orch_backend.store import NodeGraphStore, StoreError


class PatchValidationError(Exception):
    """Raised when a proposed patch violates structural or permission rules."""


# ---------------- op dataclasses ----------------

@dataclass
class AddNodeOp:
    kind: NodeKind
    title: str
    description: str = ""
    parent_id: Optional[str] = None
    hints: list[NodeHint] = field(default_factory=list)
    satisfies: list[str] = field(default_factory=list)
    explicit_id: Optional[str] = None  # prefixed id hint (e.g. "arch_foo") if provided


@dataclass
class ModifyNodeOp:
    node_id: str
    fields: dict[str, Any]


@dataclass
class DeleteNodeOp:
    node_id: str


@dataclass
class AddEdgeOp:
    from_id: str
    to_id: str
    kind: EdgeKind


@dataclass
class RemoveEdgeOp:
    from_id: str
    to_id: str
    kind: EdgeKind


@dataclass
class AddRepoOp:
    git_url: str
    name: str
    base_branch: str


PatchOp = Union[AddNodeOp, ModifyNodeOp, DeleteNodeOp, AddEdgeOp, RemoveEdgeOp, AddRepoOp]


@dataclass
class AppliedPatchSummary:
    added_nodes: list[str] = field(default_factory=list)
    modified_nodes: list[str] = field(default_factory=list)
    deleted_nodes: list[str] = field(default_factory=list)
    added_edges: list[tuple[str, str, str]] = field(default_factory=list)
    removed_edges: list[tuple[str, str, str]] = field(default_factory=list)
    added_repos: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "added_nodes": list(self.added_nodes),
            "modified_nodes": list(self.modified_nodes),
            "deleted_nodes": list(self.deleted_nodes),
            "added_edges": [list(t) for t in self.added_edges],
            "removed_edges": [list(t) for t in self.removed_edges],
            "added_repos": list(self.added_repos),
        }


# ---------------- parsing ----------------

_PATCH_RE = re.compile(
    r"<proposed_patch>\s*(.*?)\s*</proposed_patch>",
    re.DOTALL | re.IGNORECASE,
)


def parse_proposed_patch(text: str) -> list[PatchOp]:
    """Extract <proposed_patch>...</proposed_patch> and parse YAML ops.

    Returns empty list if no block is present.
    Raises PatchValidationError on malformed YAML or unknown op.
    """
    m = _PATCH_RE.search(text)
    if not m:
        return []
    body = m.group(1).strip()
    if not body:
        return []
    try:
        data = yaml.safe_load(body)
    except yaml.YAMLError as e:
        raise PatchValidationError(f"invalid YAML in proposed_patch: {e}") from e
    if data is None:
        return []
    if not isinstance(data, list):
        raise PatchValidationError("proposed_patch body must be a YAML list")

    ops: list[PatchOp] = []
    for i, raw in enumerate(data):
        if not isinstance(raw, dict) or "op" not in raw:
            raise PatchValidationError(f"op[{i}] missing 'op' key")
        op_name = raw["op"]
        if op_name == "add_node":
            hints = [
                NodeHint(**h) if isinstance(h, dict) else NodeHint(category=str(h), content=str(h))
                for h in (raw.get("hints") or [])
            ]
            ops.append(
                AddNodeOp(
                    kind=NodeKind(raw["kind"]),
                    title=str(raw.get("title", "")),
                    description=str(raw.get("description", "")),
                    parent_id=raw.get("parent_id"),
                    hints=hints,
                    satisfies=list(raw.get("satisfies") or []),
                    explicit_id=raw.get("id"),
                )
            )
        elif op_name == "modify_node":
            ops.append(
                ModifyNodeOp(
                    node_id=str(raw["node_id"]),
                    fields=dict(raw.get("fields") or {}),
                )
            )
        elif op_name == "delete_node":
            ops.append(DeleteNodeOp(node_id=str(raw["node_id"])))
        elif op_name == "add_edge":
            ops.append(
                AddEdgeOp(
                    from_id=str(raw["from"]),
                    to_id=str(raw["to"]),
                    kind=EdgeKind(raw["kind"]),
                )
            )
        elif op_name == "remove_edge":
            ops.append(
                RemoveEdgeOp(
                    from_id=str(raw["from"]),
                    to_id=str(raw["to"]),
                    kind=EdgeKind(raw["kind"]),
                )
            )
        elif op_name == "add_repo":
            ops.append(
                AddRepoOp(
                    git_url=str(raw["git_url"]),
                    name=str(raw["name"]),
                    base_branch=str(raw["base_branch"]),
                )
            )
        else:
            raise PatchValidationError(f"unknown op: {op_name}")
    return ops


# ---------------- executor ----------------


CloneRepoCallable = Callable[[str, str, str, str, str], Awaitable[dict[str, Any]]]
# (task_id, repo_name, git_url, base_branch, task_branch) -> {base_commit, init_commit, local_path}


class PatchProposalExecutor:
    """Apply parsed patch ops atomically against a NodeGraphStore.

    - Done-node modify/delete is forbidden (guardrail).
    - add_repo is only allowed for `arch_designer`.
    - On any failure, all ops in this batch roll back (we capture a snapshot first).
    """

    def __init__(
        self,
        store: NodeGraphStore,
        clone_repo: Optional[CloneRepoCallable] = None,
    ) -> None:
        self._store = store
        self._clone_repo = clone_repo  # used only for add_repo

    async def apply(
        self,
        task_id: str,
        actor_role: RoleName,
        ops: list[PatchOp],
    ) -> AppliedPatchSummary:
        if not ops:
            return AppliedPatchSummary()

        self._check_permissions(actor_role, ops)
        snap = _Snapshot.capture(self._store, task_id)
        summary = AppliedPatchSummary()
        try:
            for op in ops:
                await self._apply_one(task_id, actor_role, op, summary)
            return summary
        except Exception as e:
            snap.restore(self._store, task_id)
            raise PatchValidationError(str(e)) from e

    # -------- per-op dispatch --------
    async def _apply_one(
        self,
        task_id: str,
        actor_role: RoleName,
        op: PatchOp,
        summary: AppliedPatchSummary,
    ) -> None:
        if isinstance(op, AddNodeOp):
            self._apply_add_node(task_id, op, summary)
        elif isinstance(op, ModifyNodeOp):
            self._apply_modify_node(task_id, op, summary)
        elif isinstance(op, DeleteNodeOp):
            self._apply_delete_node(task_id, op, summary)
        elif isinstance(op, AddEdgeOp):
            self._apply_add_edge(task_id, op, summary)
        elif isinstance(op, RemoveEdgeOp):
            self._apply_remove_edge(task_id, op, summary)
        elif isinstance(op, AddRepoOp):
            await self._apply_add_repo(task_id, op, summary)
        else:  # pragma: no cover
            raise PatchValidationError(f"unhandled op: {op}")

    def _apply_add_node(self, task_id: str, op: AddNodeOp, summary: AppliedPatchSummary) -> None:
        node_id = op.explicit_id or NodeGraphStore.new_id(f"{op.kind.value.lower()}_")
        node = Node(
            id=node_id,
            task_id=task_id,
            kind=op.kind,
            title=op.title,
            description=op.description,
            hints=op.hints,
        )
        self._store.add_node(node)
        if op.parent_id:
            edge = Edge(
                id=NodeGraphStore.new_id("edge_"),
                task_id=task_id,
                from_id=op.parent_id,
                to_id=node_id,
                kind=EdgeKind.PARENT_OF,
            )
            self._store.add_edge(edge)
            try:
                # re-validate invariants now that the parent edge exists
                self._store.update_node(node)
            except StoreError as e:
                raise PatchValidationError(str(e)) from e
        for sat in op.satisfies:
            e2 = Edge(
                id=NodeGraphStore.new_id("edge_"),
                task_id=task_id,
                from_id=node_id,
                to_id=sat,
                kind=EdgeKind.SATISFIES,
            )
            self._store.add_edge(e2)
        summary.added_nodes.append(node_id)

    def _apply_modify_node(
        self, task_id: str, op: ModifyNodeOp, summary: AppliedPatchSummary
    ) -> None:
        node = self._store.get_node(op.node_id)
        if node is None:
            raise PatchValidationError(f"modify_node: unknown node_id={op.node_id}")
        if node.status == NodeStatus.DONE:
            raise PatchValidationError(f"cannot modify done node: {op.node_id}")
        if node.task_id != task_id:
            raise PatchValidationError(f"node {op.node_id} not in task {task_id}")

        allowed = {"title", "description", "hints_append", "design_content_append", "status"}
        for k in op.fields:
            if k not in allowed:
                raise PatchValidationError(f"unknown modify_node field: {k}")
        if "title" in op.fields:
            node.title = str(op.fields["title"])
        if "description" in op.fields:
            node.description = str(op.fields["description"])
        if "hints_append" in op.fields:
            for h in op.fields["hints_append"] or []:
                node.hints.append(
                    NodeHint(**h) if isinstance(h, dict) else NodeHint(category="background", content=str(h))
                )
        if "design_content_append" in op.fields:
            addition = str(op.fields["design_content_append"])
            node.design_content = (node.design_content + "\n" + addition) if node.design_content else addition
        if "status" in op.fields:
            target = op.fields["status"]
            if target != "deprecated":
                raise PatchValidationError("agent can only set status=deprecated")
            node.status = NodeStatus.DEPRECATED

        self._store.update_node(node)
        summary.modified_nodes.append(op.node_id)

    def _apply_delete_node(
        self, task_id: str, op: DeleteNodeOp, summary: AppliedPatchSummary
    ) -> None:
        node = self._store.get_node(op.node_id)
        if node is None:
            raise PatchValidationError(f"delete_node: unknown node_id={op.node_id}")
        if node.task_id != task_id:
            raise PatchValidationError(f"node {op.node_id} not in task {task_id}")
        if node.status not in (NodeStatus.PENDING, NodeStatus.DESIGN_PENDING):
            raise PatchValidationError(
                f"delete forbidden in status={node.status.value}"
            )
        self._store.delete_node(op.node_id)
        summary.deleted_nodes.append(op.node_id)

    def _apply_add_edge(
        self, task_id: str, op: AddEdgeOp, summary: AppliedPatchSummary
    ) -> None:
        edge = Edge(
            id=NodeGraphStore.new_id("edge_"),
            task_id=task_id,
            from_id=op.from_id,
            to_id=op.to_id,
            kind=op.kind,
        )
        self._store.add_edge(edge)
        summary.added_edges.append((op.from_id, op.to_id, op.kind.value))

    def _apply_remove_edge(
        self, task_id: str, op: RemoveEdgeOp, summary: AppliedPatchSummary
    ) -> None:
        self._store.remove_edge(op.from_id, op.to_id, op.kind)
        summary.removed_edges.append((op.from_id, op.to_id, op.kind.value))

    async def _apply_add_repo(
        self, task_id: str, op: AddRepoOp, summary: AppliedPatchSummary
    ) -> None:
        task = self._store.get_task(task_id)
        if task is None:
            raise PatchValidationError(f"add_repo: unknown task {task_id}")
        if self._clone_repo is None:
            raise PatchValidationError("add_repo: no RepoManager configured")
        try:
            result = await self._clone_repo(
                task_id, op.name, op.git_url, op.base_branch, task.task_branch
            )
        except Exception as e:
            raise PatchValidationError(f"clone_repo failed: {e}") from e
        repo = Repo(
            id=NodeGraphStore.new_id("repo_"),
            task_id=task_id,
            name=op.name,
            git_url=op.git_url,
            base_branch=op.base_branch,
            task_branch=task.task_branch,
            base_commit_hash=result.get("base_commit_hash", ""),
            init_commit_hash=result.get("init_commit_hash", ""),
            local_path=result.get("local_path", ""),
        )
        self._store.add_repo(repo)
        summary.added_repos.append(
            {
                "name": repo.name,
                "git_url": repo.git_url,
                "base_branch": repo.base_branch,
                "task_branch": repo.task_branch,
                "init_commit_hash": repo.init_commit_hash,
                "local_path": repo.local_path,
            }
        )

    # -------- permissions --------
    @staticmethod
    def _check_permissions(actor_role: RoleName, ops: list[PatchOp]) -> None:
        for op in ops:
            if isinstance(op, AddRepoOp) and actor_role != "arch_designer":
                raise PatchValidationError(
                    f"add_repo is only allowed for arch_designer, not {actor_role}"
                )


# ---------------- snapshot for rollback ----------------


@dataclass
class _Snapshot:
    nodes: list[Node]
    edges: list[Edge]
    repos: list[Repo]

    @classmethod
    def capture(cls, store: NodeGraphStore, task_id: str) -> "_Snapshot":
        return cls(
            nodes=list(store.list_nodes(task_id)),
            edges=list(store.list_edges(task_id)),
            repos=list(store.list_repos(task_id)),
        )

    def restore(self, store: NodeGraphStore, task_id: str) -> None:
        """Wipe current task state and reinsert snapshotted rows."""
        with store._lock:  # type: ignore[attr-defined]
            store._conn.execute("DELETE FROM nodes WHERE task_id=?", (task_id,))  # type: ignore[attr-defined]
            store._conn.execute("DELETE FROM edges WHERE task_id=?", (task_id,))  # type: ignore[attr-defined]
            store._conn.execute("DELETE FROM repos WHERE task_id=?", (task_id,))  # type: ignore[attr-defined]
        for n in self.nodes:
            store.add_node(n)
        for e in self.edges:
            store.add_edge(e)
        for r in self.repos:
            store.add_repo(r)
