"""TraeAgentAdapter + profile helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from orch_backend.adapters.trae import (
    TraeAgentAdapter,
    ensure_playwright_profile,
    materialize_trae_config_with_profile,
    shipped_default_trae_config,
)


def test_shipped_default_config_exists_and_has_playwright_mcp():
    p = shipped_default_trae_config()
    assert p.is_file()
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert "playwright" in data.get("mcp_servers", {})
    assert "playwright" in data.get("allow_mcp_servers", [])


def test_ensure_playwright_profile_creates_dir(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("ORCH_BROWSER_PROFILE_DIR", raising=False)
    p, bootstrap = ensure_playwright_profile()
    assert p == home / ".orch" / "browser-profiles" / "default"
    assert p.is_dir()
    assert bootstrap is True


def test_ensure_playwright_profile_respects_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ORCH_BROWSER_PROFILE_DIR", str(tmp_path / "custom"))
    p, bootstrap = ensure_playwright_profile()
    assert p == tmp_path / "custom"


def test_materialize_injects_user_data_dir(tmp_path: Path):
    base = tmp_path / "in.yaml"
    base.write_text(
        yaml.safe_dump(
            {"mcp_servers": {"playwright": {"command": "npx", "args": ["-y"]}}},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    prof = tmp_path / "prof"
    prof.mkdir()
    dest = tmp_path / "out.yaml"
    materialize_trae_config_with_profile(base, prof, dest)
    out = yaml.safe_load(dest.read_text(encoding="utf-8"))
    args = out["mcp_servers"]["playwright"]["args"]
    idx = args.index("--user-data-dir")
    assert args[idx + 1] == str(prof)


@pytest.mark.asyncio
async def test_trae_adapter_resolve_config_priority(tmp_path: Path):
    ws = tmp_path / "task_ws"
    ws.mkdir(parents=True)
    custom = ws / ".orch"
    custom.mkdir(parents=True)
    user_file = tmp_path / "user.yaml"
    user_file.write_text("x: 1\n", encoding="utf-8")
    (custom / "trae_config.yaml").write_text("y: 2\n", encoding="utf-8")

    a = TraeAgentAdapter(default_config_path=shipped_default_trae_config())

    from orch_backend.adapters.base import SessionHandle

    h1 = SessionHandle(
        session_id="s",
        role_name="arch_designer",
        cwd=str(ws),
        env={"ORCH_TRAE_CONFIG_PATH": str(user_file)},
    )
    assert a.resolve_config_path(ws, h1) == user_file

    h2 = SessionHandle(
        session_id="s",
        role_name="arch_designer",
        cwd=str(ws),
        env={},
    )
    assert a.resolve_config_path(ws, h2) == custom / "trae_config.yaml"


@pytest.mark.asyncio
async def test_trae_adapter_send_builds_correct_cmd(monkeypatch, tmp_path: Path):
    captured: dict = {}

    class FakeProc:
        returncode = 0

        async def communicate(self):  # type: ignore
            return b"stdout-tail", b""

    async def fake_exec(*cmd, cwd=None, env=None, stdout=None, stderr=None):
        captured["cmd"] = list(cmd)
        captured["cwd"] = cwd
        return FakeProc()

    import asyncio

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    ws = tmp_path / "ws"
    ws.mkdir(parents=True)
    a = TraeAgentAdapter(default_config_path=shipped_default_trae_config())
    from orch_backend.adapters.base import SessionHandle

    h = await a.start_session("arch_designer", "SYS", str(ws))
    await a.send(h, "USER BODY")

    cmd = captured["cmd"]
    assert "run" in cmd
    i = cmd.index("--config-file")
    cfg_path = Path(cmd[i + 1])
    assert cfg_path.is_file()
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert "playwright" in data.get("mcp_servers", {})

    pf = cmd.index("--file") + 1
    prompt = Path(cmd[pf]).read_text(encoding="utf-8")
    assert "SYS" in prompt and "USER BODY" in prompt

