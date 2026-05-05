"""FastAPI route tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from orch_backend.api.main import AppContext, build_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("ORCH_BROWSER_PROFILE_DIR", raising=False)
    ctx = AppContext(
        db_path=tmp_path / "t.db",
        workspace_base=tmp_path / "workspaces",
        trae_binary="/bin/true",  # adapter register may succeed
    )
    app = build_app(ctx)
    with TestClient(app) as c:
        yield c
    ctx.close()


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_system_status_includes_playwright_fields(client):
    r = client.get("/system/status").json()
    assert "playwright_profile_dir" in r
    assert isinstance(r["playwright_profile_bootstrap"], bool)
    assert r["playwright_profile_bootstrap"] is True  # fresh tmp HOME


def test_list_adapters_phase1(client):
    names = {a["name"] for a in client.get("/adapters").json()}
    assert "mock" in names


def test_create_task_minimal(client):
    r = client.post(
        "/tasks",
        json={"title": "t", "root_requirement": "build X"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "t"
    assert data["task_branch"].startswith("orch/")
    assert data["ppe_lane"] is None


def test_create_task_with_ppe_lane_and_branch(client):
    r = client.post(
        "/tasks",
        json={
            "title": "t",
            "root_requirement": "X",
            "task_branch": "feat/x",
            "ppe_lane": "gray-1",
        },
    )
    assert r.status_code == 200 and r.json()["ppe_lane"] == "gray-1"
    assert r.json()["task_branch"] == "feat/x"


def test_create_task_rejects_legacy_repos_spec(client):
    r = client.post(
        "/tasks",
        json={
            "title": "t",
            "root_requirement": "X",
            "repos_spec": [{"git_url": "x"}],
        },
    )
    assert r.status_code == 422


def test_create_task_rejects_legacy_max_rounds(client):
    r = client.post(
        "/tasks",
        json={
            "title": "t",
            "root_requirement": "X",
            "max_design_rounds_req": 3,
        },
    )
    assert r.status_code == 422


def test_create_task_requires_title(client):
    r = client.post("/tasks", json={"title": "", "root_requirement": "x"})
    assert r.status_code == 422


def test_get_task_404(client):
    assert client.get("/tasks/nope").status_code == 404


def test_list_and_get_task(client):
    r = client.post("/tasks", json={"title": "t1", "root_requirement": "x"})
    tid = r.json()["id"]
    listed = client.get("/tasks").json()
    assert any(t["id"] == tid for t in listed)
    detail = client.get(f"/tasks/{tid}").json()
    assert detail["task"]["id"] == tid
    assert detail["nodes"] == [] and detail["repos"] == []


def test_post_conversation_persists_user_turn(client):
    r = client.post("/tasks", json={"title": "t", "root_requirement": "x"})
    tid = r.json()["id"]
    r2 = client.post(
        f"/tasks/{tid}/conversations",
        json={"role": "arch_designer", "message": "hello @node", "referenced_node_ids": []},
    )
    assert r2.status_code == 200
    turns = client.get(f"/tasks/{tid}/turns").json()
    assert any(t["role"] == "human" and t["output_text"] == "hello @node" for t in turns)


def test_post_conversation_bad_node_ref_400(client):
    r = client.post("/tasks", json={"title": "t", "root_requirement": "x"})
    tid = r.json()["id"]
    r2 = client.post(
        f"/tasks/{tid}/conversations",
        json={"role": "arch_designer", "message": "x", "referenced_node_ids": ["nope"]},
    )
    assert r2.status_code == 400


def test_hitl_approve_gate1_advances_stage(client):
    tid = client.post("/tasks", json={"title": "t", "root_requirement": "x"}).json()["id"]
    r = client.post(
        f"/tasks/{tid}/hitl",
        json={"gate": "gate1", "action": "approve"},
    )
    assert r.status_code == 200
    detail = client.get(f"/tasks/{tid}").json()
    assert detail["task"]["stage"] == "arch_battle_running"


def test_hitl_reject_without_comment_422(client):
    tid = client.post("/tasks", json={"title": "t", "root_requirement": "x"}).json()["id"]
    r = client.post(
        f"/tasks/{tid}/hitl",
        json={"gate": "gate1", "action": "reject_with_comment", "comment": "  "},
    )
    assert r.status_code == 422


def test_archive_task(client):
    tid = client.post("/tasks", json={"title": "t", "root_requirement": "x"}).json()["id"]
    assert client.post(f"/tasks/{tid}/archive").status_code == 200
    detail = client.get(f"/tasks/{tid}").json()
    assert detail["task"]["stage"] == "archived"


def test_ws_sends_hello(client):
    tid = client.post("/tasks", json={"title": "t", "root_requirement": "x"}).json()["id"]
    with client.websocket_connect(f"/ws/tasks/{tid}") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "Hello" and hello["task_id"] == tid
