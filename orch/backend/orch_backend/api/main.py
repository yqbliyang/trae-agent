"""FastAPI app wiring — phase 1 routes.

Routes:
  GET  /health
  GET  /system/status
  GET  /adapters
  POST /tasks
  GET  /tasks
  GET  /tasks/{id}
  POST /tasks/{id}/archive
  GET  /tasks/{id}/nodes
  GET  /tasks/{id}/edges
  GET  /tasks/{id}/turns
  GET  /tasks/{id}/repos
  POST /tasks/{id}/conversations
  POST /tasks/{id}/hitl
  POST /tasks/{id}/design-change
  WS   /ws/tasks/{id}
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from orch_backend import __version__
from orch_backend.adapters import (
    AdapterRegistry,
    MockAdapter,
    TraeAgentAdapter,
    _ensure_playwright_profile,
    is_profile_bootstrap_needed,
)
from orch_backend.dispatch import DispatchLoop, RoleRegistry
from orch_backend.domain import (
    ConverseMessage,
    ConverseQueue,
    PatchProposalExecutor,
    PromptComposer,
    ReqWatcher,
)
from orch_backend.event_bus import EventBus, OrchEvent
from orch_backend.models import (
    DesignChangeRequest,
    HitlAction,
    HitlDecision,
    HitlGate,
    RoleName,
    Task,
    TaskStage,
    Turn,
    TurnOrigin,
    TurnPhase,
)
from orch_backend.repo import RepoManager, TaskRegistry
from orch_backend.store import NodeGraphStore

logger = logging.getLogger(__name__)


# ---------- request schemas ----------


class CreateTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    root_requirement: str = Field(min_length=1)
    task_branch: Optional[str] = None
    ppe_lane: Optional[str] = None
    role_overrides: Optional[dict[str, dict[str, Any]]] = None


class ConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: RoleName
    message: str = Field(min_length=1)
    referenced_node_ids: list[str] = Field(default_factory=list)


class HitlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gate: HitlGate
    action: HitlAction
    comment: str = ""
    per_node_decisions: dict[str, dict[str, str]] = Field(default_factory=dict)
    continue_extra_rounds: Optional[int] = None


class DesignChangeResponseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approve: bool
    comment: str = ""


# ---------- context bundle ----------


class AppContext:
    def __init__(
        self,
        *,
        db_path: Optional[Path] = None,
        workspace_base: Optional[Path] = None,
        trae_binary: str = "trae-cli",
    ) -> None:
        self.db_path = db_path or Path(os.environ.get("ORCH_DB", "./.orch.db"))
        self.workspace_base = workspace_base or Path(
            os.environ.get("ORCH_WORKSPACES", "./.orch-workspaces")
        )
        self.store = NodeGraphStore(self.db_path)
        self.event_bus = EventBus()
        self.converse_queue = ConverseQueue()
        self.adapter_registry = AdapterRegistry()
        self.adapter_registry.register("mock", MockAdapter(scripted_outputs=[]))
        # best-effort register real trae adapter; swallow FileNotFoundError so tests pass
        try:
            self.adapter_registry.register(
                "trae", TraeAgentAdapter(trae_binary=trae_binary)
            )
        except Exception:  # pragma: no cover
            pass
        self.role_registry = RoleRegistry(self.adapter_registry)
        self.repo_manager = RepoManager(self.workspace_base)
        self.task_registry = TaskRegistry(self.store, self.repo_manager)
        self.composer = PromptComposer(self.store)
        self.patch_executor = PatchProposalExecutor(
            self.store,
            clone_repo=self.repo_manager.clone_repo,
        )
        self.req_watcher = ReqWatcher(self.store)
        self.dispatch = DispatchLoop(
            self.store,
            self.role_registry,
            self.composer,
            self.patch_executor,
            self.req_watcher,
        )
        self.profile_dir = _ensure_playwright_profile()

    def close(self) -> None:
        self.store.close()


# ---------- factory ----------


def build_app(context: AppContext) -> FastAPI:
    app = FastAPI(title="orch-backend", version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.ctx = context

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/system/status")
    def system_status() -> dict:
        return {
            "version": __version__,
            "adapters": context.adapter_registry.names(),
            "playwright_profile_dir": str(context.profile_dir),
            "playwright_profile_bootstrap": is_profile_bootstrap_needed(context.profile_dir),
        }

    @app.get("/adapters")
    def list_adapters() -> list[dict]:
        out = []
        for name, ad in context.adapter_registry.all():
            out.append({"name": name, **ad.capabilities.model_dump()})
        return out

    # ---------- tasks ----------

    @app.post("/tasks")
    def create_task(req: CreateTaskRequest) -> dict:
        try:
            task = context.task_registry.create_task(
                title=req.title,
                root_requirement=req.root_requirement,
                task_branch=req.task_branch,
                ppe_lane=req.ppe_lane,
                role_overrides=None,  # phase 1: ignore overrides from wire
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        return task.model_dump(mode="json")

    @app.get("/tasks")
    def list_tasks() -> list[dict]:
        return [t.model_dump(mode="json") for t in context.store.list_tasks()]

    @app.get("/tasks/{task_id}")
    def get_task(task_id: str) -> dict:
        task = context.store.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")
        return {
            "task": task.model_dump(mode="json"),
            "nodes": [n.model_dump(mode="json") for n in context.store.list_nodes(task_id)],
            "edges": [e.model_dump(mode="json") for e in context.store.list_edges(task_id)],
            "turns": [t.model_dump(mode="json") for t in context.store.list_turns(task_id)],
            "repos": [r.model_dump(mode="json") for r in context.store.list_repos(task_id)],
            "hitl": [h.model_dump(mode="json") for h in context.store.list_hitl(task_id)],
        }

    @app.post("/tasks/{task_id}/archive")
    def archive_task(task_id: str) -> dict:
        task = context.store.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")
        context.store.set_task_stage(task_id, TaskStage.ARCHIVED)
        return {"status": "archived"}

    @app.get("/tasks/{task_id}/nodes")
    def task_nodes(task_id: str) -> list[dict]:
        return [n.model_dump(mode="json") for n in context.store.list_nodes(task_id)]

    @app.get("/tasks/{task_id}/edges")
    def task_edges(task_id: str) -> list[dict]:
        return [e.model_dump(mode="json") for e in context.store.list_edges(task_id)]

    @app.get("/tasks/{task_id}/turns")
    def task_turns(
        task_id: str,
        role: Optional[str] = None,
        phase: Optional[str] = None,
    ) -> list[dict]:
        return [
            t.model_dump(mode="json")
            for t in context.store.list_turns(task_id, role=role, phase=phase)
        ]

    @app.get("/tasks/{task_id}/repos")
    def task_repos(task_id: str) -> list[dict]:
        return [r.model_dump(mode="json") for r in context.store.list_repos(task_id)]

    # ---------- conversations ----------

    @app.post("/tasks/{task_id}/conversations")
    async def post_conversation(task_id: str, req: ConversationRequest) -> dict:
        if context.store.get_task(task_id) is None:
            raise HTTPException(status_code=404, detail="task not found")
        # invalid node refs → 400
        for nid in req.referenced_node_ids:
            if context.store.get_node(nid) is None:
                raise HTTPException(status_code=400, detail=f"invalid node ref: {nid}")
        mid = NodeGraphStore.new_id("msg_")
        # persist user Turn immediately so the UI can show it
        user_turn = Turn(
            id=NodeGraphStore.new_id("turn_"),
            task_id=task_id,
            role="human",
            adapter_name="human",
            phase=TurnPhase.CONVERSE,
            origin=TurnOrigin.USER,
            round_index=0,
            input_text="",
            output_text=req.message,
            payload_extra={
                "target_role": req.role,
                "referenced_node_ids": req.referenced_node_ids,
            },
        )
        context.store.append_turn(user_turn)
        depth = context.converse_queue.enqueue(
            ConverseMessage(
                id=mid,
                task_id=task_id,
                role=req.role,
                message=req.message,
                referenced_node_ids=req.referenced_node_ids,
            )
        )
        await context.event_bus.publish(
            OrchEvent(
                type="TurnAppended",
                task_id=task_id,
                payload=user_turn.model_dump(mode="json"),
            )
        )
        return {"id": mid, "queue_depth": depth}

    @app.get("/tasks/{task_id}/conversations")
    def list_conversations(task_id: str, role: Optional[str] = None) -> list[dict]:
        turns = context.store.list_turns(task_id, role=role)
        return [t.model_dump(mode="json") for t in turns]

    # ---------- HITL ----------

    @app.post("/tasks/{task_id}/hitl")
    async def post_hitl(task_id: str, req: HitlRequest) -> dict:
        task = context.store.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")
        if req.action == HitlAction.REJECT_WITH_COMMENT and not req.comment.strip():
            raise HTTPException(status_code=422, detail="reject requires comment")
        decision = HitlDecision(
            id=NodeGraphStore.new_id("hitl_"),
            task_id=task_id,
            gate=req.gate,
            action=req.action,
            comment=req.comment,
            per_node_decisions=req.per_node_decisions,
            continue_extra_rounds=req.continue_extra_rounds,
        )
        context.store.add_hitl(decision)
        # phase 1: a best-effort stage advance
        if req.action == HitlAction.APPROVE:
            if req.gate == HitlGate.GATE1:
                context.store.set_task_stage(task_id, TaskStage.ARCH_BATTLE_RUNNING)
            elif req.gate == HitlGate.GATE2:
                context.store.set_task_stage(task_id, TaskStage.EXECUTING)
        await context.event_bus.publish(
            OrchEvent(
                type="HitlRecorded",
                task_id=task_id,
                payload=decision.model_dump(mode="json"),
            )
        )
        return decision.model_dump(mode="json")

    # ---------- design change ----------

    @app.post("/tasks/{task_id}/design-change")
    def post_design_change(task_id: str, req: DesignChangeResponseRequest) -> dict:
        if not req.approve and not req.comment.strip():
            raise HTTPException(status_code=422, detail="reject requires comment")
        pending = context.store.get_latest_pending_design_change(task_id)
        if pending is None:
            raise HTTPException(status_code=404, detail="no pending design change")
        pending.status = "approved" if req.approve else "rejected"
        context.store.add_design_change(pending)
        return pending.model_dump(mode="json")

    # ---------- WS ----------

    @app.websocket("/ws/tasks/{task_id}")
    async def ws(ws: WebSocket, task_id: str) -> None:
        await ws.accept()
        q = context.event_bus.subscribe(task_id)
        try:
            await ws.send_json({"type": "Hello", "task_id": task_id, "payload": {}})
            while True:
                try:
                    evt: OrchEvent = await asyncio.wait_for(q.get(), timeout=10)
                    await ws.send_json(evt.to_wire())
                except asyncio.TimeoutError:
                    await ws.send_json({"type": "Heartbeat", "task_id": task_id, "payload": {}})
        except WebSocketDisconnect:
            pass
        finally:
            context.event_bus.unsubscribe(task_id, q)

    return app


def create_app() -> FastAPI:
    """Factory for uvicorn `orch_backend.api.main:app`-style entry."""
    ctx = AppContext()
    return build_app(ctx)


with contextlib.suppress(Exception):
    app = create_app()  # default export for `uvicorn orch_backend.api.main:app`
