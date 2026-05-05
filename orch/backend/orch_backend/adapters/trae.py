"""TraeAgentAdapter — subprocess-boundary implementation (decoupled from trae_agent imports)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Optional

import yaml

from orch_backend.adapters.base import (
    AdapterError,
    AssistantReply,
    CodingAgentAdapter,
    SessionHandle,
    StreamCallback,
    StreamEvent,
)
from orch_backend.models import AdapterCapabilities

log = logging.getLogger("orch_backend.trae_adapter")


def shipped_default_trae_config() -> Path:
    """Resolved path of `config/trae_default.yaml` next to backend root."""
    return Path(__file__).resolve().parents[2] / "config" / "trae_default.yaml"


def ensure_playwright_profile(
    environ: Optional[dict[str, str]] = None,
) -> tuple[Path, bool]:
    """Create browser profile dir if missing; returns (path, bootstrap_flag).

    `bootstrap_flag` is True when the directory was just created or Chromium
    has not populated `Default/` yet → user probably needs first-time login guidance.
    """
    env_map = environ or os.environ
    raw = env_map.get("ORCH_BROWSER_PROFILE_DIR", "").strip()
    if raw:
        p = Path(raw).expanduser()
    else:
        p = Path.home() / ".orch" / "browser-profiles" / "default"
    created_now = False
    if not p.exists():
        p.mkdir(parents=True, exist_ok=True)
        created_now = True
    chromium_default = p / "Default"
    bootstrap = created_now or not chromium_default.exists()
    return p, bootstrap


def materialize_trae_config_with_profile(
    base_yaml: Path, profile_dir: Path, dest: Path
) -> None:
    """Merge Playwright MCP user-data-dir into a temp config file."""

    data = yaml.safe_load(base_yaml.read_text(encoding="utf-8"))
    mcp = data.setdefault("mcp_servers", {}).setdefault("playwright", {})
    args = list(mcp.get("args") or [])
    # strip any old --user-data-dir
    filtered: list[str] = []
    skip_next = False
    for a in args:
        if skip_next:
            skip_next = False
            continue
        if a.startswith("--user-data-dir="):
            continue
        if a == "--user-data-dir":
            skip_next = True
            continue
        filtered.append(a)
    filtered.extend(["--user-data-dir", str(profile_dir)])
    mcp["args"] = filtered
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


class TraeAgentAdapter(CodingAgentAdapter):
    """Phase-1 real adapter (optional invocation of `trae-cli`)."""

    capabilities: AdapterCapabilities = AdapterCapabilities(
        name="trae", supports_session_resume=False, supports_streaming=True
    )

    def __init__(
        self,
        *,
        trae_binary: str | None = None,
        default_config_path: Path | None = None,
        timeout_sec: float = 3600,
    ) -> None:
        self._timeout = timeout_sec
        self._binary = (
            trae_binary
            or shutil.which("trae-cli")
            or shutil.which("trae_cli")
            or "trae-cli"
        )
        self._default_config = Path(
            default_config_path or shipped_default_trae_config()
        )
        self.profile_dir, _ = ensure_playwright_profile()

    def resolve_config_path(
        self,
        workspace_path: Path,
        session: SessionHandle,
    ) -> Path:
        """Highest priority: env ORCH_TRAE_CONFIG_PATH → workspace → ship default."""

        candidates: list[Path] = []
        e = session.env.get("ORCH_TRAE_CONFIG_PATH", "").strip()
        if e:
            candidates.append(Path(e).expanduser())
        candidates.append(Path(workspace_path) / ".orch" / "trae_config.yaml")
        candidates.append(self._default_config)

        for c in candidates:
            if c.is_file():
                return c
        return self._default_config

    async def start_session(
        self,
        role_name: str,
        system_prompt: str,
        cwd: str,
        env: Optional[dict[str, str]] = None,
    ) -> SessionHandle:
        return SessionHandle(
            session_id=os.urandom(4).hex(),
            role_name=role_name,
            cwd=cwd,
            env=dict(env or {}),
            state={"system_prompt": system_prompt},
        )

    async def send(
        self,
        session: SessionHandle,
        user_message: str,
        stream_cb: StreamCallback | None = None,
    ) -> AssistantReply:
        workspace = Path(session.cwd).expanduser()
        orch_dir = workspace / ".orch"
        orch_dir.mkdir(parents=True, exist_ok=True)
        traj = orch_dir / f"trajectory_{session.role_name}_{session.session_id}.jsonl"

        user_cfg_raw = self.resolve_config_path(workspace, session)
        runtime_cfg = orch_dir / f"runtime_trae_{session.session_id}.yaml"
        profile_dir, _ = ensure_playwright_profile()
        materialize_trae_config_with_profile(user_cfg_raw, profile_dir, runtime_cfg)

        prompt_path = orch_dir / f"prompt_{session.session_id}.txt"
        full_prompt = session.state["system_prompt"] + "\n\n---\n\n" + user_message
        prompt_path.write_text(full_prompt, encoding="utf-8")

        cmd = [
            self._binary,
            "run",
            "--file",
            str(prompt_path),
            "--config-file",
            str(runtime_cfg),
            "--working-dir",
            str(workspace),
            "--trajectory-file",
            str(traj),
            "--console-type",
            "simple",
        ]

        merged_env = {**os.environ, **session.env}

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(workspace),
            env=merged_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=self._timeout)
        except asyncio.TimeoutError as e:
            proc.kill()
            raise AdapterError("trae-cli subprocess timeout") from e

        if proc.returncode != 0:
            raise AdapterError(
                f"trae-cli exited {proc.returncode}: {err.decode(errors='ignore')[:2000]}"
            )

        text = ""
        artifacts: list[str] = []
        if traj.exists():
            artifacts.append(str(traj))
            text = await self._read_final_assistant(traj)

        tail = _tail_text(out.decode(errors="ignore"), n=16000)
        if not text:
            text = tail

        if stream_cb is not None:
            chunk = max(512, len(text) // 8 or 8)
            for i in range(0, len(text), chunk):
                await stream_cb(StreamEvent(kind="token", text=text[i : i + chunk]))
            await stream_cb(StreamEvent(kind="end"))

        return AssistantReply(
            text=text,
            artifacts=artifacts,
            extra={"stderr": err.decode(errors="ignore")},
        )

    async def end_session(self, session: SessionHandle) -> None:
        return

    def resolve_artifacts(self, session: SessionHandle) -> list[str]:
        workspace = Path(session.cwd) / ".orch"
        traj = workspace / f"trajectory_{session.role_name}_{session.session_id}.jsonl"
        if traj.exists():
            return [str(traj)]
        return []


def _tail_text(s: str, n: int) -> str:
    return s if len(s) <= n else s[-n:]


async def _read_final_assistant(traj: Path) -> str:
    """Best-effort: read last trajectory line carrying assistant content."""

    if not traj.exists():
        return ""
    lines = traj.read_text(encoding="utf-8", errors="ignore").splitlines()
    for raw in reversed(lines[-200:]):
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            txt = row.get("content") or row.get("message") or row.get("text") or ""
            role = str(row.get("role", "")).lower()
            if role in ("assistant", "model", "ai") and txt:
                return str(txt)
    return ""


# ---- API / wiring aliases (plan M12 / M15) ----


def _ensure_playwright_profile(
    environ: Optional[dict[str, str]] = None,
) -> Path:
    p, _ = ensure_playwright_profile(environ)
    return p


def is_profile_bootstrap_needed(profile_dir: Path) -> bool:
    """True when Chromium hasn't created `Default/` yet (first-time login likely)."""

    return not (profile_dir / "Default").is_dir()


DEFAULT_SHIPPED_CONFIG: Path = shipped_default_trae_config()
