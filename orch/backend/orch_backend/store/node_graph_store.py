"""NodeGraphStore — SQLite persistence for nodes/edges/tasks/turns/hitl/repos.

Intentionally synchronous (sqlite3) under an asyncio.Lock so it is trivially safe
to call from async code; performance is more than enough for phase 1.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Iterable, Optional

from orch_backend.models import (
    DesignChangeRequest,
    Edge,
    EdgeKind,
    HitlDecision,
    Node,
    NodeFailureEvent,
    NodeKind,
    NodeStatus,
    Repo,
    Task,
    TaskStage,
    Turn,
)


class StoreError(Exception):
    """Raised for any store-level invariant violation or IO failure."""


_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_nodes_task ON nodes(task_id);
CREATE TABLE IF NOT EXISTS edges (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    from_id TEXT NOT NULL,
    to_id TEXT NOT NULL,
    kind TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_edges_task ON edges(task_id);
CREATE TABLE IF NOT EXISTS turns (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    role TEXT NOT NULL,
    phase TEXT NOT NULL,
    origin TEXT NOT NULL,
    round_index INTEGER NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_turns_task ON turns(task_id, created_at);
CREATE TABLE IF NOT EXISTS hitl (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS repos (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    name TEXT NOT NULL,
    payload TEXT NOT NULL,
    UNIQUE(task_id, name)
);
CREATE TABLE IF NOT EXISTS design_changes (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS node_failures (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    payload TEXT NOT NULL
);
"""


class NodeGraphStore:
    """Synchronous SQLite store with a process-wide lock."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._db_path = str(db_path)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            self._db_path, check_same_thread=False, isolation_level=None
        )
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @staticmethod
    def new_id(prefix: str = "") -> str:
        short = uuid.uuid4().hex[:12]
        return f"{prefix}{short}" if prefix else short

    # ---------- tasks ----------
    def upsert_task(self, task: Task) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO tasks(id,payload) VALUES(?,?)",
                (task.id, task.model_dump_json()),
            )

    def get_task(self, task_id: str) -> Optional[Task]:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM tasks WHERE id=?", (task_id,)
            ).fetchone()
        if not row:
            return None
        return Task.model_validate_json(row[0])

    def list_tasks(self) -> list[Task]:
        with self._lock:
            rows = self._conn.execute("SELECT payload FROM tasks").fetchall()
        return [Task.model_validate_json(r[0]) for r in rows]

    def set_task_stage(self, task_id: str, stage: TaskStage) -> None:
        task = self.get_task(task_id)
        if not task:
            raise StoreError(f"task not found: {task_id}")
        task.stage = stage
        self.upsert_task(task)

    # ---------- nodes ----------
    def add_node(self, node: Node) -> None:
        self._validate_node_invariants(node)
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO nodes(id,task_id,kind,status,payload) VALUES(?,?,?,?,?)",
                (node.id, node.task_id, node.kind.value, node.status.value, node.model_dump_json()),
            )

    def update_node(self, node: Node) -> None:
        existing = self.get_node(node.id)
        if existing is None:
            raise StoreError(f"node not found: {node.id}")
        self._validate_node_invariants(node)
        with self._lock:
            self._conn.execute(
                "UPDATE nodes SET kind=?, status=?, payload=? WHERE id=?",
                (node.kind.value, node.status.value, node.model_dump_json(), node.id),
            )

    def delete_node(self, node_id: str) -> None:
        existing = self.get_node(node_id)
        if not existing:
            raise StoreError(f"node not found: {node_id}")
        if existing.status in (NodeStatus.RUNNING, NodeStatus.DONE):
            raise StoreError(
                f"cannot delete node {node_id} in status={existing.status.value}"
            )
        with self._lock:
            self._conn.execute("DELETE FROM nodes WHERE id=?", (node_id,))
            self._conn.execute(
                "DELETE FROM edges WHERE from_id=? OR to_id=?", (node_id, node_id)
            )

    def get_node(self, node_id: str) -> Optional[Node]:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM nodes WHERE id=?", (node_id,)
            ).fetchone()
        if not row:
            return None
        return Node.model_validate_json(row[0])

    def list_nodes(self, task_id: str) -> list[Node]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload FROM nodes WHERE task_id=?", (task_id,)
            ).fetchall()
        return [Node.model_validate_json(r[0]) for r in rows]

    # ---------- edges ----------
    def add_edge(self, edge: Edge) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO edges(id,task_id,from_id,to_id,kind) VALUES(?,?,?,?,?)",
                (edge.id, edge.task_id, edge.from_id, edge.to_id, edge.kind.value),
            )

    def remove_edge(self, from_id: str, to_id: str, kind: EdgeKind) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM edges WHERE from_id=? AND to_id=? AND kind=?",
                (from_id, to_id, kind.value),
            )

    def list_edges(self, task_id: str) -> list[Edge]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id,task_id,from_id,to_id,kind FROM edges WHERE task_id=?",
                (task_id,),
            ).fetchall()
        return [
            Edge(
                id=r[0], task_id=r[1], from_id=r[2], to_id=r[3], kind=EdgeKind(r[4])
            )
            for r in rows
        ]

    # ---------- turns ----------
    def append_turn(self, turn: Turn) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO turns(id,task_id,role,phase,origin,round_index,payload,created_at)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (
                    turn.id,
                    turn.task_id,
                    turn.role,
                    turn.phase.value,
                    turn.origin.value,
                    turn.round_index,
                    turn.model_dump_json(),
                    turn.created_at.isoformat(),
                ),
            )

    def list_turns(
        self,
        task_id: str,
        role: Optional[str] = None,
        phase: Optional[str] = None,
    ) -> list[Turn]:
        sql = "SELECT payload FROM turns WHERE task_id=?"
        params: list = [task_id]
        if role:
            sql += " AND role=?"
            params.append(role)
        if phase:
            sql += " AND phase=?"
            params.append(phase)
        sql += " ORDER BY created_at ASC"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [Turn.model_validate_json(r[0]) for r in rows]

    # ---------- hitl ----------
    def add_hitl(self, decision: HitlDecision) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO hitl(id,task_id,payload) VALUES(?,?,?)",
                (decision.id, decision.task_id, decision.model_dump_json()),
            )

    def list_hitl(self, task_id: str) -> list[HitlDecision]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload FROM hitl WHERE task_id=?", (task_id,)
            ).fetchall()
        return [HitlDecision.model_validate_json(r[0]) for r in rows]

    # ---------- repos ----------
    def add_repo(self, repo: Repo) -> None:
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT INTO repos(id,task_id,name,payload) VALUES(?,?,?,?)",
                    (repo.id, repo.task_id, repo.name, repo.model_dump_json()),
                )
            except sqlite3.IntegrityError as e:
                raise StoreError(f"repo name collision: {repo.name}") from e

    def list_repos(self, task_id: str) -> list[Repo]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload FROM repos WHERE task_id=?", (task_id,)
            ).fetchall()
        return [Repo.model_validate_json(r[0]) for r in rows]

    # ---------- design changes ----------
    def add_design_change(self, req: DesignChangeRequest) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO design_changes(id,task_id,payload) VALUES(?,?,?)",
                (req.id, req.task_id, req.model_dump_json()),
            )

    def get_latest_pending_design_change(
        self, task_id: str
    ) -> Optional[DesignChangeRequest]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload FROM design_changes WHERE task_id=?", (task_id,)
            ).fetchall()
        reqs = [DesignChangeRequest.model_validate_json(r[0]) for r in rows]
        pending = [r for r in reqs if r.status == "pending"]
        return pending[-1] if pending else None

    # ---------- node failures ----------
    def add_node_failure(self, evt: NodeFailureEvent) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO node_failures(id,task_id,payload) VALUES(?,?,?)",
                (evt.id, evt.task_id, evt.model_dump_json()),
            )

    # ---------- invariants ----------
    def _validate_node_invariants(self, node: Node) -> None:
        """Enforce core structural rules from plan §3.

        - ARCH cannot have an ARCH ancestor in the current task.
        - CODE/TEST's parent (via parent_of edge) must be ARCH.
        Note: we check parent relationships only when edges already exist.
        """
        if node.kind == NodeKind.ARCH:
            for anc in self._ancestors(node.task_id, node.id):
                if anc.kind == NodeKind.ARCH and anc.id != node.id:
                    raise StoreError(
                        f"ARCH nesting forbidden: {node.id} has ARCH ancestor {anc.id}"
                    )
        if node.kind in (NodeKind.CODE, NodeKind.TEST):
            parents = self._parents(node.task_id, node.id)
            if parents and not any(p.kind == NodeKind.ARCH for p in parents):
                raise StoreError(
                    f"{node.kind.value} parent must be ARCH: node={node.id}"
                )

    def _parents(self, task_id: str, node_id: str) -> list[Node]:
        edges = self.list_edges(task_id)
        parent_ids = [e.from_id for e in edges if e.to_id == node_id and e.kind == EdgeKind.PARENT_OF]
        return [p for p in (self.get_node(pid) for pid in parent_ids) if p is not None]

    def _ancestors(self, task_id: str, node_id: str) -> Iterable[Node]:
        seen: set[str] = set()
        frontier = [node_id]
        while frontier:
            cur = frontier.pop()
            if cur in seen:
                continue
            seen.add(cur)
            for p in self._parents(task_id, cur):
                yield p
                frontier.append(p.id)
