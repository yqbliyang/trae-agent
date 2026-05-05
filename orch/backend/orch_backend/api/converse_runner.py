"""Process ConverseQueue messages through the active adapter (phase 1)."""

from __future__ import annotations

from orch_backend.domain.converse_queue import ConverseQueue
from orch_backend.domain.patch_executor import (
    PatchProposalExecutor,
    PatchValidationError,
    parse_proposed_patch,
)
from orch_backend.domain.prompt_composer import PromptComposer
from orch_backend.domain.req_watcher import ReqWatcher
from orch_backend.dispatch.role_registry import RoleRegistry
from orch_backend.event_bus import EventBus, OrchEvent
from orch_backend.models import RoleName, Turn, TurnOrigin, TurnPhase
from orch_backend.store import NodeGraphStore


class ConverseRunner:
    """Drain one converse message for (task_id, role) → adapter Turn + optional patches."""

    def __init__(
        self,
        *,
        store: NodeGraphStore,
        queue: ConverseQueue,
        role_registry: RoleRegistry,
        composer: PromptComposer,
        patches: PatchProposalExecutor,
        req_watcher: ReqWatcher | None,
        event_bus: EventBus,
    ) -> None:
        self.store = store
        self.queue = queue
        self.roles = role_registry
        self.composer = composer
        self.patches = patches
        self.req_watcher = req_watcher
        self.events = event_bus

    async def process_one(self, task_id: str, role: RoleName) -> Turn | None:
        msg = self.queue.pop(task_id, role)
        if msg is None:
            return None

        task = self.store.get_task(task_id)
        if task is None:
            return None

        refs = ", ".join(msg.referenced_node_ids) if msg.referenced_node_ids else "(none)"
        instruction = (
            f"用户发来的对话请求（已通过 ConverseQueue 送达）：\n{msg.message}\n\n"
            f"referenced_node_ids: [{refs}]\n"
            "若需改图，请输出 <proposed_patch>；否则给自然语言回复即可。"
        )

        sess = await self.roles.get_or_create_session(
            task, role, self.composer.system_prompt_for(role)
        )
        prompt = self.composer.compose_for_role(
            task=task,
            role=role,
            current_instruction=instruction,
            adapter=sess.adapter,
        )

        try:
            reply = await sess.adapter.send(sess.handle, prompt)
        except Exception as e:  # noqa: BLE001
            err_turn = Turn(
                id=NodeGraphStore.new_id("turn_"),
                task_id=task_id,
                role=role,
                adapter_name=sess.adapter_name,
                phase=TurnPhase.CONVERSE,
                origin=TurnOrigin.CONVERSE,
                round_index=0,
                input_text=instruction[:8000],
                output_text=f"[ADAPTER_ERROR] {e}",
                payload_extra={
                    "converse_message_id": msg.id,
                    "error": True,
                },
            )
            self.store.append_turn(err_turn)
            await self.events.publish(
                OrchEvent(
                    type="TurnAppended",
                    task_id=task_id,
                    payload=err_turn.model_dump(mode="json"),
                )
            )
            return err_turn

        applied = await self._apply_patch_if_any(task_id, role, reply.text)

        extra: dict = {"converse_message_id": msg.id}
        if applied is not None:
            extra["applied_patch_summary"] = applied.to_dict()

        agent_turn = Turn(
            id=NodeGraphStore.new_id("turn_"),
            task_id=task_id,
            role=role,
            adapter_name=sess.adapter_name,
            phase=TurnPhase.CONVERSE,
            origin=TurnOrigin.CONVERSE,
            round_index=0,
            input_text=prompt[:8000],
            output_text=reply.text,
            payload_extra=extra,
        )
        self.store.append_turn(agent_turn)
        await self.events.publish(
            OrchEvent(
                type="TurnAppended",
                task_id=task_id,
                payload=agent_turn.model_dump(mode="json"),
            )
        )
        if applied is not None and (
            applied.added_nodes
            or applied.modified_nodes
            or applied.added_edges
            or applied.added_repos
        ):
            await self.events.publish(
                OrchEvent(
                    type="GraphUpdated",
                    task_id=task_id,
                    payload={
                        "node_count": len(self.store.list_nodes(task_id)),
                        "edge_count": len(self.store.list_edges(task_id)),
                        "repo_count": len(self.store.list_repos(task_id)),
                    },
                )
            )
        return agent_turn

    async def _apply_patch_if_any(
        self, task_id: str, role: RoleName, text: str
    ):
        try:
            ops = parse_proposed_patch(text)
        except PatchValidationError:
            await self._system_feedback(task_id, role, "patch YAML 非法")
            return None
        if not ops:
            return None
        try:
            summary = await self.patches.apply(task_id, role, ops)
        except PatchValidationError as e:
            await self._system_feedback(task_id, role, str(e))
            return None
        if self.req_watcher is not None:
            self.req_watcher.notify(task_id, summary)
        return summary

    async def _system_feedback(self, task_id: str, role: RoleName, err: str) -> None:
        msg = self.composer.compose_validation_error_reply(err)
        t = Turn(
            id=NodeGraphStore.new_id("turn_"),
            task_id=task_id,
            role="system",
            adapter_name="system",
            phase=TurnPhase.SYSTEM,
            origin=TurnOrigin.SYSTEM,
            round_index=0,
            input_text="",
            output_text=msg,
            payload_extra={"for_role": role},
        )
        self.store.append_turn(t)
        await self.events.publish(
            OrchEvent(
                type="TurnAppended",
                task_id=task_id,
                payload=t.model_dump(mode="json"),
            )
        )
