"""RepoManager — clone repos into a task workspace + empty commit anchor."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any


class RepoCloneError(Exception):
    pass


class RepoManager:
    """Wraps `git clone / checkout / commit --allow-empty` as a small async API.

    Args:
        base_dir: root directory where task workspaces live.
        git_binary: git binary to call (default: "git").
    """

    def __init__(
        self,
        base_dir: Path | str,
        git_binary: str = "git",
    ) -> None:
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)
        self._git = git_binary

    def workspace_for(self, task_id: str) -> Path:
        wp = self._base / task_id
        wp.mkdir(parents=True, exist_ok=True)
        return wp

    async def clone_repo(
        self,
        task_id: str,
        repo_name: str,
        git_url: str,
        base_branch: str,
        task_branch: str,
    ) -> dict[str, Any]:
        """Clone `git_url` into `<workspace>/<repo_name>`, switch to task_branch,
        make an empty commit. Returns metadata dict.
        """
        workspace = self.workspace_for(task_id)
        local_path = workspace / repo_name
        if local_path.exists():
            raise RepoCloneError(f"repo already cloned: {local_path}")

        try:
            await self._run_git(
                [self._git, "clone", "--branch", base_branch, git_url, str(local_path)],
                cwd=workspace,
            )
        except Exception as e:
            if local_path.exists():
                shutil.rmtree(local_path, ignore_errors=True)
            raise RepoCloneError(f"clone failed: {e}") from e

        base_commit = await self._capture_git(
            [self._git, "rev-parse", "HEAD"], cwd=local_path
        )
        await self._run_git(
            [self._git, "checkout", "-b", task_branch], cwd=local_path
        )
        # minimum git user config so the empty commit doesn't explode on fresh CI hosts
        await self._run_git(
            [self._git, "config", "user.email", "orch@local"], cwd=local_path
        )
        await self._run_git(
            [self._git, "config", "user.name", "orch"], cwd=local_path
        )
        await self._run_git(
            [
                self._git,
                "commit",
                "--allow-empty",
                "-m",
                f"chore(orch): task anchor for {task_id}",
            ],
            cwd=local_path,
        )
        init_commit = await self._capture_git(
            [self._git, "rev-parse", "HEAD"], cwd=local_path
        )

        return {
            "local_path": str(local_path),
            "base_commit_hash": base_commit,
            "init_commit_hash": init_commit,
        }

    # ---------- helpers ----------

    async def _run_git(self, cmd: list[str], cwd: Path) -> None:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        if proc.returncode != 0:
            raise RepoCloneError(
                f"git {' '.join(cmd[1:])} failed: rc={proc.returncode} err={err.decode(errors='ignore')}"
            )

    async def _capture_git(self, cmd: list[str], cwd: Path) -> str:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        if proc.returncode != 0:
            raise RepoCloneError(
                f"git {' '.join(cmd[1:])} failed: {err.decode(errors='ignore')}"
            )
        return out.decode().strip()
