"""ReqWatcher — if REQ tree mutates at Gate 2, bounce stage back to arch_battle_running."""

from __future__ import annotations

from typing import Callable, Optional

from orch_backend.domain.patch_executor import AppliedPatchSummary
from orch_backend.models import NodeKind, TaskStage
from orch_backend.store import NodeGraphStore


class ReqWatcher:
    """Subscribes to applied-patch summaries; if a REQ node was touched while the
    task is GATE2_WAITING, it sets stage back to ARCH_BATTLE_RUNNING and fires
    `on_rewind(task_id)` so the dispatch layer can enqueue another arch_designer pass.
    """

    def __init__(
        self,
        store: NodeGraphStore,
        on_rewind: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._store = store
        self._on_rewind = on_rewind

    def notify(self, task_id: str, summary: AppliedPatchSummary) -> bool:
        task = self._store.get_task(task_id)
        if task is None or task.stage != TaskStage.GATE2_WAITING:
            return False
        affected = set(summary.added_nodes) | set(summary.modified_nodes) | set(summary.deleted_nodes)
        if not affected:
            return False
        for nid in affected:
            # deleted nodes may be gone — we can't know their kind post-fact;
            # be conservative: also count 'deleted' as a REQ touch.
            n = self._store.get_node(nid)
            if n is None or n.kind == NodeKind.REQ:
                self._store.set_task_stage(task_id, TaskStage.ARCH_BATTLE_RUNNING)
                if self._on_rewind is not None:
                    self._on_rewind(task_id)
                return True
        return False
