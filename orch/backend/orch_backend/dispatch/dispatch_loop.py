"""DispatchLoop — orchestrates battle rounds + converge detection.

Phase 1 keeps it synchronous per task (a single asyncio.Task drives each Task).

Battle loop for a pair (proposer, critic) against a single instruction:
  round 1: proposer → critic
  round 2: proposer (re-asked with critic feedback) → critic
  ...
Convergence triggers:
  - critic's latest output contains `[CONVERGED]`  (explicit)
  - critic's two consecutive outputs hash-equal    (implicit)
  - round count reaches DEFAULT_MAX_ROUNDS (=5)    (timeout → HITL)
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Optional

from orch_backend.adapters import AdapterError, StreamEvent
from orch_backend.dispatch.role_registry import RoleRegistry
from orch_backend.domain.patch_executor import (
    AppliedPatchSummary,
    PatchProposalExecutor,
    PatchValidationError,
    parse_proposed_patch,
)
from orch_backend.domain.prompt_composer import PromptComposer
from orch_backend.domain.req_watcher import ReqWatcher
from orch_backend.models import (
    DEFAULT_MAX_ROUNDS,
    RoleName,
    Task,
    Turn,
    TurnOrigin,
    TurnPhase,
)
from orch_backend.store import NodeGraphStore


@dataclass
class BattleOutcome:
    converged: bool
    reason: str  # "explicit" | "implicit" | "max_rounds"
    rounds: int
    proposer_last: str = ""
    critic_last: str = ""
    applied_summaries: list[AppliedPatchSummary] = field(default_factory=list)


class DispatchLoop:
    """One-shot battle runner for a (proposer, critic) pair.

    The caller supplies the initial instruction; the loop builds prompts via
    PromptComposer, calls adapters, persists Turns, applies patches, and
    returns BattleOutcome.
    """

    def __init__(
        self,
        store: NodeGraphStore,
        role_registry: RoleRegistry,
        prompt_composer: PromptComposer,
        patch_executor: PatchProposalExecutor,
        req_watcher: Optional[ReqWatcher] = None,
    ) -> None:
        self.store = store
        self.roles = role_registry
        self.prompts = prompt_composer
        self.patches = patch_executor
        self.req_watcher = req_watcher

    async def run_battle(
        self,
        task: Task,
        proposer: RoleName,
        critic: RoleName,
        initial_instruction: str,
        phase: TurnPhase,
        max_rounds: int = DEFAULT_MAX_ROUNDS,
    ) -> BattleOutcome:
        """Drive up to `max_rounds` proposer↔critic rounds; return outcome."""
        proposer_sess = await self.roles.get_or_create_session(
            task, proposer, self.prompts.system_prompt_for(proposer)
        )
        critic_sess = await self.roles.get_or_create_session(
            task, critic, self.prompts.system_prompt_for(critic)
        )

        outcome = BattleOutcome(converged=False, reason="max_rounds", rounds=0)
        critic_history: list[str] = []
        last_proposer_text = ""
        last_critic_text = ""
        proposer_instruction = initial_instruction

        for r in range(1, max_rounds + 1):
            outcome.rounds = r

            # --- proposer ---
            proposer_prompt = self.prompts.compose_for_role(
                task=task,
                role=proposer,
                current_instruction=proposer_instruction,
                adapter=proposer_sess.adapter,
            )
            try:
                proposer_reply = await proposer_sess.adapter.send(
                    proposer_sess.handle, proposer_prompt
                )
            except AdapterError as e:
                raise RuntimeError(f"proposer adapter error: {e}") from e
            last_proposer_text = proposer_reply.text

            p_summary = await self._apply_patch_if_any(
                task.id, proposer, proposer_reply.text
            )
            self._record_turn(
                task=task,
                role=proposer,
                adapter_name=proposer_sess.adapter_name,
                phase=phase,
                round_index=r,
                input_text=proposer_instruction,
                output_text=proposer_reply.text,
                origin=TurnOrigin.BATTLE,
                applied_summary=p_summary,
            )

            # --- critic ---
            critic_instruction = (
                f"Proposer ({proposer}) round {r} output:\n\n"
                f"{proposer_reply.text}\n\n"
                f"请给出你的审视意见（若完全通过，附 [CONVERGED]）。"
            )
            critic_prompt = self.prompts.compose_for_role(
                task=task,
                role=critic,
                current_instruction=critic_instruction,
                adapter=critic_sess.adapter,
            )
            try:
                critic_reply = await critic_sess.adapter.send(
                    critic_sess.handle, critic_prompt
                )
            except AdapterError as e:
                raise RuntimeError(f"critic adapter error: {e}") from e
            last_critic_text = critic_reply.text

            c_summary = await self._apply_patch_if_any(
                task.id, critic, critic_reply.text
            )
            self._record_turn(
                task=task,
                role=critic,
                adapter_name=critic_sess.adapter_name,
                phase=phase,
                round_index=r,
                input_text=critic_instruction,
                output_text=critic_reply.text,
                origin=TurnOrigin.BATTLE,
                applied_summary=c_summary,
            )

            critic_history.append(critic_reply.text)

            # --- converge detection ---
            if "[CONVERGED]" in critic_reply.text:
                outcome.converged = True
                outcome.reason = "explicit"
                break
            if len(critic_history) >= 2 and _digest(critic_history[-1]) == _digest(
                critic_history[-2]
            ):
                outcome.converged = True
                outcome.reason = "implicit"
                break

            # Next round's proposer input: carry critic feedback forward
            proposer_instruction = (
                f"critic 上一轮反馈：\n{critic_reply.text}\n\n请据此修订你的上一次产出。"
            )

        outcome.proposer_last = last_proposer_text
        outcome.critic_last = last_critic_text
        return outcome

    async def _apply_patch_if_any(
        self, task_id: str, role: RoleName, text: str
    ) -> Optional[AppliedPatchSummary]:
        try:
            ops = parse_proposed_patch(text)
        except PatchValidationError as e:
            # record an error Turn so the next round sees the feedback
            await self._record_system_feedback(task_id, role, str(e))
            return None
        if not ops:
            return None
        try:
            summary = await self.patches.apply(task_id, role, ops)
        except PatchValidationError as e:
            await self._record_system_feedback(task_id, role, str(e))
            return None
        if self.req_watcher is not None:
            self.req_watcher.notify(task_id, summary)
        return summary

    async def _record_system_feedback(
        self, task_id: str, role: RoleName, err: str
    ) -> None:
        msg = self.prompts.compose_validation_error_reply(err)
        self.store.append_turn(
            Turn(
                id=NodeGraphStore.new_id("turn_"),
                task_id=task_id,
                role="system",
                adapter_name="system",
                phase=TurnPhase.SYSTEM,
                origin=TurnOrigin.SYSTEM,
                round_index=0,
                input_text="",
                output_text=msg,
                payload_extra={"for_role": role, "kind": "validation_error"},
            )
        )

    def _record_turn(
        self,
        task: Task,
        role: RoleName,
        adapter_name: str,
        phase: TurnPhase,
        round_index: int,
        input_text: str,
        output_text: str,
        origin: TurnOrigin,
        applied_summary: Optional[AppliedPatchSummary],
    ) -> None:
        extra: dict = {}
        if applied_summary is not None:
            extra["applied_patch_summary"] = applied_summary.to_dict()
        self.store.append_turn(
            Turn(
                id=NodeGraphStore.new_id("turn_"),
                task_id=task.id,
                role=role,
                adapter_name=adapter_name,
                phase=phase,
                origin=origin,
                round_index=round_index,
                input_text=input_text,
                output_text=output_text,
                payload_extra=extra,
            )
        )


def _digest(text: str) -> str:
    """SHA1 digest of text stripped of marker + whitespace."""
    cleaned = text.replace("[CONVERGED]", "").strip()
    return hashlib.sha1(cleaned.encode("utf-8")).hexdigest()
