"""PromptComposer — turns Task + Node + history into a prompt for an adapter.

Strategy is selected by AdapterCapabilities.supports_session_resume:
- False → inject last K turns' output_text verbatim (phase 1 TraeAgentAdapter path).
- True  → emit artifact-index resume hints only.

In phase 1 we only support K=5 and string-level templates (no Jinja loading from disk
to keep the test surface small).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from orch_backend.adapters.base import CodingAgentAdapter
from orch_backend.models import RoleName, Task, Turn
from orch_backend.store import NodeGraphStore


PREAMBLE = """\
你是 orchestrator 下属的一个角色 agent（具体角色见下文），通过 CodingAgentAdapter 协议被驱动。
# 运行环境
- cwd 为某个 Task 的独占 workspace 根；workspace 下挂若干独立 clone 的 git 代码仓库。
- 跨仓库引用一律用字符串约定 `repo:<name>/<path>` 表达。
- 每个 repo 的 task_branch 上有一个空 commit 作为"任务起点锚点"，你的改动都发生在它之后。
# 外部文档读取（Playwright MCP）
- 你已接入 Playwright MCP，可直接用 `browser_navigate` / `browser_snapshot` 访问飞书 / Notion / Confluence 等登录态文档；profile 是持久化的，未登录请提示用户完成一次登录后重试。
# 如何修改节点图
任何节点图改动只能通过在回复中输出 `<proposed_patch>...</proposed_patch>` 表达，YAML op 列表会被 orchestrator 立即原子应用。
# 机读标记
- `[CONVERGED]`：battle 收敛
- `[NODE_DONE]` / `[NODE_FAILED] reason=...`：执行期节点完结
- `[DESIGN_CHANGE_REQUEST]`：执行期请求暂停审批设计变更
- `[VALIDATION_ERROR]`：系统回传（你收到后应修正后重试）
"""


ROLE_SYSTEM_PROMPTS: dict[str, str] = {
    "req_decomposer": (
        "你的角色：req_decomposer（需求理解与拆解者）。\n"
        "使命：把用户的 root_requirement 拆成合理颗粒度的 REQ 节点树，标注 AI hints。\n"
        "产出：`<proposed_patch>` 中用 add_node 建 REQ 节点、add_edge 组织 parent_of 关系；"
        "每个叶 REQ 要能独立落地为一个 ARCH。完成时请在回复末尾附 [CONVERGED] 表示你认为拆分已足够。"
    ),
    "req_completeness_critic": (
        "你的角色：req_completeness_critic（需求拆分完整性校验者）。\n"
        "使命：审视当前 REQ 树对 root_requirement 的覆盖度，给出清单化的未覆盖点。\n"
        "若无未覆盖项，请在回复末尾附 [CONVERGED]。"
    ),
    "arch_designer": (
        "你的角色：arch_designer（全局架构设计者）。\n"
        "使命：对已通过 Gate 1 的 REQ 树，逐一生成 ARCH 节点并挂 CODE/TEST 骨架（TDD：先 TEST 后 CODE）。\n"
        "SDD 要求：优先最小修改历史代码；所有下游调用给出完整参数契约；字段必须标注 source_ref。\n"
        "若需要新仓库才能完成设计，请用 `add_repo` op 声明（只有你有此权限）。\n"
        "执行期若遇到既有设计明显错误，你可以在 `<proposed_patch>` 里微调；若改动较大，请改用 "
        "[DESIGN_CHANGE_REQUEST] 标记并暂停等待用户批准。收敛后附 [CONVERGED]。"
    ),
    "arch_coverage_critic": (
        "你的角色：arch_coverage_critic（全局架构覆盖完整性校验者）。\n"
        "使命：针对每个 REQ 检查 ARCH 是否覆盖、字段 source_ref 是否齐全、TDD 测试规划是否完整。\n"
        "若全部通过，回复末尾附 [CONVERGED]。"
    ),
}


@dataclass
class PromptComposer:
    store: NodeGraphStore
    history_k: int = 5

    def system_prompt_for(self, role: RoleName) -> str:
        role_block = ROLE_SYSTEM_PROMPTS.get(role, "")
        return PREAMBLE + "\n\n" + role_block

    def compose_for_role(
        self,
        task: Task,
        role: RoleName,
        current_instruction: str,
        adapter: Optional[CodingAgentAdapter] = None,
    ) -> str:
        """Build the user-facing prompt body to pass to adapter.send()."""
        lines: list[str] = []
        lines.append(f"# Task: {task.title} (id={task.id})")
        lines.append(f"task_branch: {task.task_branch}")
        if task.ppe_lane:
            lines.append(f"ppe_lane: {task.ppe_lane}")
        repos = self.store.list_repos(task.id)
        if repos:
            lines.append("# Cloned repos:")
            for r in repos:
                lines.append(f"- {r.name} (branch={r.task_branch}, path={r.local_path})")
        else:
            lines.append("# Cloned repos: (none — arch_designer may declare via add_repo)")
        lines.append("")
        lines.append("# Root requirement")
        lines.append(task.root_requirement)
        lines.append("")

        # Node tree (compact)
        nodes = self.store.list_nodes(task.id)
        if nodes:
            lines.append("# Current node graph (compact)")
            for n in sorted(nodes, key=lambda x: (x.kind.value, x.id)):
                lines.append(f"- [{n.kind.value} {n.id}] {n.title} (status={n.status.value})")
            lines.append("")

        # Recent turns (prompt-injection resume)
        use_injection = True
        if adapter is not None and adapter.capabilities.supports_session_resume:
            use_injection = False
        if use_injection:
            turns = self.store.list_turns(task.id)[-self.history_k:]
            if turns:
                lines.append(f"# Recent {len(turns)} turns (memory via prompt injection)")
                for t in turns:
                    lines.append(f"## [{t.role} / round={t.round_index}]")
                    lines.append(t.output_text.strip())
                    lines.append("")

        lines.append("# Your task this round")
        lines.append(current_instruction)
        return "\n".join(lines)

    def compose_validation_error_reply(self, error_text: str) -> str:
        """System-side feedback to send back to the role after a patch rejection."""
        return (
            "[VALIDATION_ERROR] 你的上一次 `<proposed_patch>` 未通过校验：\n"
            f"{error_text}\n"
            "请根据错误原因修改后重新输出 patch。"
        )
