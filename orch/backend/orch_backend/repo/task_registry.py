"""TaskRegistry — create tasks with empty workspace + auto task_branch."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from orch_backend.models import Task, TaskStage
from orch_backend.repo.repo_manager import RepoManager
from orch_backend.store import NodeGraphStore


def slugify_title(title: str, max_len: int = 40) -> str:
    s = unicodedata.normalize("NFKD", title)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return (s or "task")[:max_len]


class TaskRegistry:
    def __init__(self, store: NodeGraphStore, repo_manager: RepoManager) -> None:
        self.store = store
        self.repos = repo_manager

    def create_task(
        self,
        title: str,
        root_requirement: str,
        task_branch: str | None = None,
        ppe_lane: str | None = None,
        role_overrides: dict | None = None,
    ) -> Task:
        task_id = NodeGraphStore.new_id("task_")
        short = task_id.replace("task_", "")[:8]
        branch = task_branch or f"orch/{short}/{slugify_title(title)}"
        workspace_path = str(self.repos.workspace_for(task_id))
        Path(workspace_path, ".orch").mkdir(parents=True, exist_ok=True)
        task = Task(
            id=task_id,
            title=title,
            root_requirement=root_requirement,
            workspace_path=workspace_path,
            task_branch=branch,
            ppe_lane=ppe_lane,
            stage=TaskStage.REQ_BATTLE_RUNNING,
            role_config_override=role_overrides or {},
        )
        self.store.upsert_task(task)
        return task
