"""RepoManager + TaskRegistry."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path

import pytest

from orch_backend.repo import RepoCloneError, RepoManager, TaskRegistry


def _git_available() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


git_required = pytest.mark.skipif(not _git_available(), reason="git not available")


@pytest.fixture()
def local_bare_repo(tmp_path: Path) -> Path:
    """Create a minimal local bare-ish git repo for clone tests."""
    src = tmp_path / "upstream"
    src.mkdir()
    subprocess.run(["git", "init", "-b", "master", str(src)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(src), "config", "user.email", "u@x"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(src), "config", "user.name", "u"], check=True, capture_output=True)
    (src / "README.md").write_text("hello")
    subprocess.run(["git", "-C", str(src), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(src), "commit", "-m", "init"], check=True, capture_output=True)
    return src


def test_task_registry_creates_empty_workspace_no_repos(tmp_path, store):
    rm = RepoManager(tmp_path / "workspaces")
    reg = TaskRegistry(store, rm)
    task = reg.create_task("my feature", "do X")
    assert Path(task.workspace_path).exists()
    assert (Path(task.workspace_path) / ".orch").exists()
    assert store.list_repos(task.id) == []


def test_task_registry_autogen_task_branch(tmp_path, store):
    rm = RepoManager(tmp_path / "workspaces")
    reg = TaskRegistry(store, rm)
    task = reg.create_task("My Feature Name!", "X")
    assert task.task_branch.startswith("orch/")
    assert "my-feature-name" in task.task_branch.lower()


def test_task_registry_accepts_explicit_task_branch(tmp_path, store):
    rm = RepoManager(tmp_path / "workspaces")
    reg = TaskRegistry(store, rm)
    task = reg.create_task("t", "x", task_branch="custom/branch")
    assert task.task_branch == "custom/branch"


def test_task_registry_accepts_ppe_lane(tmp_path, store):
    rm = RepoManager(tmp_path / "workspaces")
    reg = TaskRegistry(store, rm)
    task = reg.create_task("t", "x", ppe_lane="gray-9")
    assert task.ppe_lane == "gray-9"


@git_required
def test_repo_manager_clone_creates_task_branch_with_empty_commit(tmp_path, local_bare_repo):
    rm = RepoManager(tmp_path / "ws")
    meta = asyncio.run(
        rm.clone_repo(
            task_id="t1",
            repo_name="login",
            git_url=str(local_bare_repo),
            base_branch="master",
            task_branch="orch/t1/feat",
        )
    )
    assert Path(meta["local_path"]).exists()
    assert meta["base_commit_hash"] != meta["init_commit_hash"]
    # verify current branch is the task_branch
    out = subprocess.run(
        ["git", "-C", meta["local_path"], "rev-parse", "--abbrev-ref", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    assert out == "orch/t1/feat"


@git_required
def test_repo_manager_refuses_duplicate_clone(tmp_path, local_bare_repo):
    rm = RepoManager(tmp_path / "ws")
    asyncio.run(
        rm.clone_repo("t1", "login", str(local_bare_repo), "master", "orch/t1/x")
    )
    with pytest.raises(RepoCloneError):
        asyncio.run(
            rm.clone_repo("t1", "login", str(local_bare_repo), "master", "orch/t1/x")
        )


@git_required
def test_repo_manager_cleanup_on_bad_url(tmp_path):
    rm = RepoManager(tmp_path / "ws")
    with pytest.raises(RepoCloneError):
        asyncio.run(
            rm.clone_repo("t1", "login", "/definitely/not/a/real/path", "master", "orch/t1/x")
        )
    # partial dir cleaned
    assert not (tmp_path / "ws" / "t1" / "login").exists()
