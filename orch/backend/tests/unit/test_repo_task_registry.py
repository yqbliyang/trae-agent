"""RepoManager + TaskRegistry tests."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

from orch_backend.repo import RepoManager, TaskRegistry
from orch_backend.store import NodeGraphStore


def _init_bare_git(path: Path, branch: str = "master") -> None:
    subprocess.run(
        ["git", "init", "--bare", "-b", branch, str(path)],
        check=True,
        capture_output=True,
    )


@pytest.mark.asyncio
async def test_repo_manager_clone_empty_commit(tmp_path: Path):
    bare = tmp_path / "origin.git"
    _init_bare_git(bare)

    # make an initial commit reachable on master
    work = tmp_path / "push_work"
    subprocess.run(["git", "clone", str(bare), str(work)], check=True, capture_output=True)
    (work / "README.md").write_text("init\n")
    subprocess.run(["git", "-C", str(work), "config", "user.email", "x@y"], check=True)
    subprocess.run(["git", "-C", str(work), "config", "user.name", "x"], check=True)
    subprocess.run(["git", "-C", str(work), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(work), "commit", "-m", "init"], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(work), "push", "origin", "master"], check=True, capture_output=True
    )

    mgr = RepoManager(tmp_path / "workspaces")
    meta = await mgr.clone_repo(
        task_id="task_123",
        repo_name="login",
        git_url=str(bare),
        base_branch="master",
        task_branch="orch/tb/x",
    )
    assert Path(meta["local_path"]).is_dir()
    assert len(meta["base_commit_hash"]) == 40
    assert len(meta["init_commit_hash"]) == 40
    assert meta["base_commit_hash"] != meta["init_commit_hash"]

    # HEAD is on task_branch
    head_branch = subprocess.run(
        ["git", "-C", meta["local_path"], "branch", "--show-current"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert head_branch == "orch/tb/x"


@pytest.mark.asyncio
async def test_repo_manager_cleanup_on_clone_failure(tmp_path: Path):
    mgr = RepoManager(tmp_path / "workspaces")
    with pytest.raises(Exception):
        await mgr.clone_repo(
            task_id="t1",
            repo_name="broken",
            git_url="https://example.com/does-not-exist-orch-test.git",
            base_branch="master",
            task_branch="orch/x",
        )
    assert not (mgr.workspace_for("t1") / "broken").exists()


def test_task_registry_create_empty_workspace(store, tmp_path: Path):
    mgr = RepoManager(tmp_path / "workspaces")
    reg = TaskRegistry(store, mgr)
    t = reg.create_task(title="My Title!", root_requirement="req text")
    disk = Path(t.workspace_path)
    assert disk.is_dir()
    assert t.task_branch.startswith("orch/")
    assert t.ppe_lane is None
    assert store.get_task(t.id) is not None


def test_task_registry_autogen_branch_format(store, tmp_path: Path):
    mgr = RepoManager(tmp_path / "workspaces")
    reg = TaskRegistry(store, mgr)
    t = reg.create_task(title="Hello World", root_requirement="r")
    # orch/<short8>/<slug>
    parts = t.task_branch.split("/")
    assert len(parts) == 3 and parts[0] == "orch"


def test_task_registry_explicit_branch(store, tmp_path: Path):
    mgr = RepoManager(tmp_path / "workspaces")
    reg = TaskRegistry(store, mgr)
    t = reg.create_task(
        title="t", root_requirement="r", task_branch="custom/feature-x"
    )
    assert t.task_branch == "custom/feature-x"


def test_task_registry_ppe_lane_optional(store, tmp_path: Path):
    mgr = RepoManager(tmp_path / "workspaces")
    reg = TaskRegistry(store, mgr)
    t = reg.create_task(title="t", root_requirement="r", ppe_lane="gray-1")
    assert t.ppe_lane == "gray-1"
