---
name: 基于trae-agent的思维导图需求拆解与SDD/TDD执行系统 - 一期全局角色极简版
overview: 在"Thin Orchestrator 版"基础上进一步简化——节点降级为纯数据载体，所有管理职能统一到 **4 个全局角色**（req_decomposer / req_completeness_critic / arch_designer / arch_coverage_critic）；节点不再挂 battle 角色。一期所有 ARCH 共享单一 arch_designer 上下文产出；**执行阶段固定用 inherit 模式**（设计者下凡落地，记忆靠 PromptComposer 拼最近 K 轮历史实现）；`fresh_small` / `fresh_large` 模式留二期。**一期唯一 adapter 是 `TraeAgentAdapter`**，但通过 `CodingAgentAdapter` Protocol 严格解耦——新增 adapter（Claude Code / Cursor / Aider 等）只需实现 5 个协议方法 + 在 `AdapterRegistry` 注册一行，无需改 orchestrator 任何代码。**系统以 Task 为顶层隔离单位，每 Task 独占一个 workspace 目录，下面可含多个独立 clone 的 Repo**；本地部署的 orchestrator 实例可同时跑多个完全隔离的 Task。完整版（节点自带 battle）保留在 [707fc8c5 版本](/Users/mima1-6/.cursor/plans/基于trae-agent的思维导图需求拆解与sdd_tdd执行系统_707fc8c5.plan.md) 作为参考。
todos: []
---

# 一期全局角色极简版 —— 需求与架构

> 架构哲学一句话：**节点只是数据，角色负责管理；全局 4 个角色跨所有节点工作，单一 arch_designer 一上下文产出整棵设计树并下凡实施。**

---

## 1. 需求描述

### 1.1 产品目标（不变）

输入复杂需求，在一棵可视化思维导图上自动展开为 REQ / ARCH / CODE / TEST 四类节点；由全局角色遍历、设计、校验；用户在关键阀门做 HITL；所有过程可审计、可回放；底层编码 CLI 可替换。

### 1.2 一期简化的核心变化（相对 707fc8c5 完整版）

| 维度 | 707fc8c5 完整版 | 本版（一期极简） |
|---|---|---|
| 节点角色 | 每节点挂 1~3 个 role 做 battle | **节点不挂 role**，仅数据载体 |
| 管理职能分布 | REQ 管自己拆分、ARCH 管 CODE/TEST | **全部上移**到 4 个全局角色 |
| ARCH 方案产出 | 每个 ARCH 独立 architect+critic 两个 session 做 battle | **单一 arch_designer session 一次产全部 ARCH/CODE/TEST** |
| 覆盖校验 | 每个 ARCH 节点各跑一次 coverage_critic | **一个全局 arch_coverage_critic 统一校验全树** |
| REQ 拆分 | 每个 REQ 各自跑 planner 单轮 | **一个全局 req_decomposer 统一拆全树** + 一个 req_completeness_critic 校验 |
| ARCH 嵌套 | 同路径唯一 ARCH | **沿用：同路径唯一 ARCH** |
| 执行阶段策略 | 节点级 battle + 节点级 HITL | **固定 inherit 模式**：`arch_designer`/`arch_coverage_critic` 带设计期记忆下凡落地 CODE/TEST；`fresh_small` / `fresh_large` 模式及对应执行角色均留二期 |
| adapter 策略 | trae 绑死 | **一期唯一 adapter = TraeAgentAdapter**，但契约完全解耦（`CodingAgentAdapter` Protocol + `AdapterRegistry`）；新增 adapter 零侵入 orchestrator；capability flag 驱动记忆策略自适配（prompt injection vs native resume） |
| 节点级 HITL 四模式 | 在每个 ARCH 节点 waiting_review 时四选一 | **收缩为双阀门**（REQ 树阀门 + ARCH 全树阀门）+ per-node 决议 + 无上限追加 battle 轮 + 随时节点引用对话 |
| 思维导图编辑 | 前端图上可增删节点 / 改 hint | **只读 + 不可操作**；所有修改由 agent 通过对话（@ 引用节点）主动输出 `<proposed_patch>` 自动应用；用户不勾选、只发消息。UI 采用**两栏主布局**（左 mindmap + 右 4 个全局角色 tab），点节点浮出 `NodeFloatingCard`（可钉），TopBar 按钮打开 `TurnAuditModal` / `ReposPopover` |
| workspace 语义 | adapter 的 cwd = 单个代码仓库根 | **Task 级 workspace**；workspace 下含多个独立 clone 的 Repo + `.orch/`；adapter 的 cwd = workspace 根（可跨仓库读写） |
| 并发任务 | 未明确 | **本地 orchestrator 支持多 Task 并发、完全隔离**（数据库按 task_id 分区，文件系统各自独立 clone） |

### 1.3 非功能需求

- **彻底解耦**：orchestrator 不 import `trae_agent` / 任何具体 CLI 的内部符号；所有交互都通过 `CodingAgentAdapter` Protocol（5 方法契约）+ `AdapterCapabilities` flag 驱动。新增 adapter 的成本 = 实现协议的一个类 + `AdapterRegistry.register()` 一行；**不需要**改 orchestrator、不需要改 PromptComposer、不需要改 DispatchLoop
- **完整审计**：每次 adapter 调用的输入/输出/原生轨迹/事件流全量 append-only
- **可恢复性**：节点级 re-dispatch + adapter 原生 resume（若支持）
- **屎山场景兼容**：hint 结构化 + 双阀门 HITL + 全量转录
- **多 Task 完全隔离**：本地 orchestrator 单实例可同时跑多 Task；Task 间数据（SQLite 按 task_id 分区）/ 文件（各自独立 workspace 目录 + 独立 repo clone）/ 角色 session 全部隔离；并发数不设上限（用户自行量力）
- **多仓库原生支持**：一个 Task 的 workspace 下可包含多个独立 clone 的代码仓库；AI 在一个 adapter 调用里可跨仓库读写；集成测试可同时启动多个 PSM 的服务

---

## 2. 总体架构

```mermaid
flowchart TB
    subgraph FE [Web Frontend]
        TL[Task 列表页]
        UI[任务详情: reactflow 只读思维导图]
        CP[对话面板（侧栏）]
        GATE1[REQ 树 HITL 阀门]
        GATE2[ARCH 全树 HITL 阀门]
    end

    subgraph Server [FastAPI + WS]
        REST[REST /tasks /converse ...]
        WSB[WS EventBus 按 task_id 分频道]
    end

    subgraph Orch [Orchestrator 单实例]
        TR[TaskRegistry<br/>追踪所有 active Task]
        RM[RepoManager<br/>clone / checkout 分支]
        NG[NodeGraphStore<br/>SQLite 按 task_id 分区]
        RA[RoleAgentRegistry<br/>每 Task 独立 4 角色 session]
        PC[PromptComposer]
        DL[DispatchLoop<br/>每 Task 一个协程并发]
    end

    subgraph Contract [反腐层]
        PROTO[CodingAgentAdapter 协议]
        AR[AdapterRegistry<br/>name 到 adapter 类的映射]
    end

    subgraph Adapters [可插拔执行器]
        ATRA["TraeAgentAdapter<br/>(一期唯一)"]
        AMOC["MockAdapter<br/>(测试用)"]
        ACLA["ClaudeCodeAdapter<br/>(二期扩展点)"]
        AAID["AiderAdapter<br/>(二期扩展点)"]
    end

    subgraph FS [本地文件系统]
        WA["workspace_task_A/<br/>├─ repo_foo/ (独立 clone)<br/>├─ repo_bar/ (独立 clone)<br/>└─ .orch/"]
        WB["workspace_task_B/<br/>├─ repo_foo/ (独立 clone)<br/>└─ .orch/"]
    end

    TL --> REST
    UI --> REST
    CP --> REST
    GATE1 --> REST
    GATE2 --> REST
    REST --> Orch
    Orch --> WSB --> UI
    DL --> PROTO
    PROTO --> AR
    AR --> ATRA
    AR -. 二期新增 .-> ACLA
    AR -. 二期新增 .-> AAID
    AR --> AMOC
    RM --> WA
    RM --> WB
    ATRA -. "cwd = workspace_task_X/" .-> WA
    ATRA -. "cwd = workspace_task_X/" .-> WB
```

### 2.1 架构边界

**Orchestrator 做**：Task 生命周期 / Repo clone 与分支管理 / 节点图 / 角色 session 管理（任务级）/ prompt 拼装 / 调度 / 审计 / HITL / 事件推送。

**Orchestrator 不做**：代码检索 / 具体文件读写 / git 提交策略 / 语义理解 / 代码修改 / 测试执行。这些都下沉到 adapter。

### 2.2 并发与隔离契约

- **任务间 SQLite 隔离**：所有节点/边/Turn 表必含 `task_id`，查询强制过滤
- **任务间文件隔离**：每 Task 独占 `workspace_<task_id>/` 目录；同一仓库被多 Task 用时**各自独立 clone**，不共享、不链接
- **任务间 session 隔离**：`RoleAgentRegistry` 按 `(task_id, role_name)` 索引，任务 A 的 `arch_designer` 和任务 B 的完全是两个 adapter session
- **任务间 WebSocket 隔离**：EventBus 按 `task_id` 分频道，前端订阅单任务频道
- **并发无上限**：一期不限制活跃 Task 数，用户自己评估机器资源 / adapter API 限流

### 2.3 术语与三层结构

| 术语 | 含义 | 1:N 关系 |
|---|---|---|
| **Task** | 一次需求任务（顶层隔离单位） | 每 Task 独占 1 个 Workspace |
| **Workspace** | Task 的文件系统根目录 | 每 Workspace 含 ≥1 个 Repo + 1 个 `.orch/` 元数据目录 |
| **Repo** | 单个代码仓库的独立 `git clone` | 每个 Repo 在 Task 创建时从 master 新切一个用户指定的 task_branch |
| **节点图** | REQ / ARCH / CODE / TEST 思维导图 | 每 Task 独享一棵节点图，SQLite 按 `task_id` 分区 |

物理结构示例：

```
/data/orch/
├── orch.sqlite3                  ← 全局 DB，所有 Task 共用，按 task_id 分区
└── workspaces/
    ├── task_abc123/              ← Workspace = Task 的 FS 根
    │   ├── repo_login/           ← Repo 1：独立 clone，切到 task_branch
    │   ├── repo_payment/         ← Repo 2：独立 clone
    │   ├── repo_frontend/        ← Repo 3：独立 clone
    │   └── .orch/
    │       └── roles/<role_name>/trajectories/<turn_id>.json
    └── task_def456/              ← 另一个 Task，完全独立
        └── repo_login/           ← 与 task_abc123/repo_login 是两份独立 clone
```

---

## 3. 数据模型（Task / Repo / Node / Edge / Turn）

### 3.0 Task 与 Repo 表

```
Task {
  id                              // uuid
  title, description              // 任务元信息
  workspace_path: str             // 绝对路径，如 /data/orch/workspaces/task_<id>
  status: created | req_battling | gate1_waiting
        | arch_battling | gate2_waiting
        | executing | done | failed | archived
  execution_mode: "inherit"       // 一期固定 inherit；字段保留，二期支持 fresh_small / fresh_large
  role_config_override: dict      // 任务创建时用户对 RoleConfig 的覆写（锁死到任务生命周期）
  task_branch: str                // 统一分支名；所有 add_repo 声明的仓库都在此分支上工作；留空由 TaskRegistry 按 orch/<short_task_id>/<title_slug> 自动生成
  ppe_lane: str | null            // PPE 泳道标识（可选）；用于 PPE 环境部署/接口测试；注入 prompt 和 adapter 环境变量 PPE_LANE
  created_at, updated_at
  // 注：一期对战轮数改为常量 DEFAULT_MAX_ROUNDS=5（见 4.1），不作为 Task 字段暴露
}

Repo {
  id, task_id                     // 每条 Repo 归属唯一 Task；由 arch_designer 运行期用 add_repo op 声明后插入，Task 创建时不预置
  name: str                       // 简短别名，在 hints 中通过 repo:<name>/<path> 引用；workspace 下的目录名
  git_url: str                    // clone 的源
  base_branch: str                // arch_designer 声明时指定；默认由其探测 master/main
  task_branch: str                // = Task.task_branch 的副本；checkout -b 到这条
  base_commit_hash: str | null    // clone 后 base_branch 的 HEAD commit（用于最终 diff 计算）
  init_commit_hash: str | null    // 在 task_branch 上创建的空 commit SHA（任务起点锚点，见 4.4）
  local_path: str                 // workspace 下的相对路径，默认 = name
  status: pending | cloning | ready | failed
  cloned_at
}
```

**Task 创建时零仓库**：Task 启动后 workspace 目录为空；首个 `add_repo` op 触发首次 clone（见 4.4.2）。REQ 阶段讨论可完全脱离代码语境，既符合 SDD 的"先理解再动手"，也把"需要哪些代码"这一判断交给真正能负责的 `arch_designer`。

**`init_commit_hash` 的关键作用**（一期引入）：
- **CKG 自动隔离**：每个 Task 首个空 commit 的 SHA 天然唯一 → trae 的 `snapshot_hash` 从 clone 瞬间就在 Task 间分化，共享同一文件系统的多个 Task 之间不会出现 `.db` 碰撞 / storage_info 冲突（见 4.4.1）
- **任务起点锚点**：用户查看 `git log task_branch` 时一眼看到"任务起点"标记；`git diff <init_commit_hash>..HEAD` 显示本 Task 所有 agent 改动
- **回滚手段**：`git reset --hard <base_commit_hash>` 可把 task_branch 回到起点前的状态（相当于丢弃整个任务的所有变更）

### 3.1 Node 通用字段

```
Node {
  id
  task_id                         // 所属 Task（所有查询必过滤）
  kind: REQ | ARCH | CODE | TEST
  title, description
  parent_id, dependencies: list[node_id]
  hints: list[NodeHint]           // 结构化，按 category + weight
  status                          // 见 3.1.2
  turns: list[Turn]               // append-only 审计
  hitl_decisions: list[HitlDecision]
  // 相对 707fc8c5 删除字段：roles, rules, inherited_hints_view
}
```

（所有 Edge / Turn / HitlDecision 表也同等加 `task_id` 列，按 `(task_id, id)` 复合主键；本文不一一重列。）

### 3.1.1 ARCH 额外字段

```
ARCH 额外字段 {
  design_content: str             // 由 arch_designer 写入（方案文本）
  managed_code_nodes: list[id]    // arch_designer 规划的 CODE 子节点
  managed_test_nodes: list[id]    // arch_designer 规划的 TEST 子节点
  aggregate_status                // 见 3.1.2
}
```

### 3.1.2 各 kind 状态机

| kind | 状态 |
|---|---|
| REQ | `pending → done / failed`（派生） |
| ARCH | `pending → filling → waiting_review → dispatching → aggregating → done / partial / failed` |
| CODE | `pending → running → done / failed` |
| TEST | `pending → running → passed / failed` |

**关键变化**：ARCH 没有 `designing / coverage_reviewing` 内部 battle 状态了——`filling` 是被动等全局 arch_designer 写入字段的过程，不做节点级 LLM 调用。

### 3.1.3 NodeHint（跨仓库引用用字符串约定）

```
NodeHint {
  id, category, content, weight, added_by, added_at
}
category ∈ { background, constraint, preference, code_pointer,
             external_ref, domain_knowledge, deployment,
             log_access, env_setup, skill_ref }
weight ∈ { must, should, nice }
```

**跨仓库引用约定**（一期用字符串前缀，不加新字段）：

- `category = code_pointer` 或 `external_ref` 的 `content` 字段可用以下格式表达跨仓库指向：

  ```
  repo:<repo_name>/<path>[#<symbol>][:L<start>-L<end>]  <自然语言描述>
  ```

  举例：
  - `repo:login/internal/handler/login.go#LoginByEmail — 原邮箱登录主流程，需要在入参结构体加 fingerprint 字段`
  - `repo:payment/api/charge_v2.proto:L30-L55 — 支付接口的现行 proto，新字段必须兼容`

- `<repo_name>` 必须是同 Task 的 `Repo.name`；`RepoManager` 可把 `repo:<name>/<path>` 解析为绝对路径 `<workspace>/<Repo.local_path>/<path>`
- 前端渲染时把 `repo:<name>/<path>` 部分识别为可点击链接（跳代码查看器或外部编辑器）
- adapter 读到这类 hint 时也可以按约定直接 `cat <workspace>/<local_path>/<path>`（adapter 的 cwd 本就是 workspace 根）

二期若发现字符串约定解析不稳，可升级为 `NodeHint.repo_ref` 结构化字段（见 11 节）。

### 3.1.4 Edge（不变，沿用 707fc8c5）

```
Edge.type ∈ { parent_of, depends_on, satisfies, covers }
```

### 3.1.5 Turn（不变，沿用 707fc8c5）

```
Turn {
  id, timestamp, role_name, adapter_name  // role_name 现在是 6 种全局角色之一
  prompt_sent, output_text
  consumed_artifacts, produced_artifacts
  adapter_events_digest
  duration_ms, token_usage
  exit_code, success, stderr_tail
}
```

### 3.1.6 HitlDecision（简化为 2+1 种动作）

```
HitlDecision {
  node_id | gate_id                // 节点级 or 阀门级
  user_id, action, payload, timestamp
}
action ∈ {
  approve,                    // 通过，进入下一阶段
  reject_with_comment,        // 打回并写评论（评论作为 must-weight hint 注入下一轮）
  approve_partial,            // 阀门级特有：树上逐节点勾（payload 含 per-node 决议 map）
  continue_battle             // 阀门级特有：用户看完双方最终论断后，手动追加 N 轮 battle；无上限
}
continue_battle.payload = { extra_rounds: int, comment: str | null }
```

**HitlDecision 回归"阀门决议"纯粹语义**：只记录用户在 Gate 上对"是否推进到下一阶段"的决策；**不记录内容修改**。
对话（converse）是运行时交互，只产生 Turn（含一条 `adapter_name="human"` 的用户消息 Turn + 一条 AI 响应 Turn），**不产生 HitlDecision**——因为用户在对话中没做"决议"，他只是**请 agent 帮忙改**，真正的修改由 agent 主动完成（见 6.4）。

### 3.1.7 图结构硬约束

```
硬约束（一期 inherit 模式全局适用）：
  1. CODE / TEST 的 parent_of 父必须是 ARCH
  2. 叶 REQ（testcase 粒度）禁止挂 ARCH
  3. 每条 REQ 根-叶路径必须被某个祖先 ARCH 覆盖（通过 satisfies/covers 或 parent_of）
  4. 同一 REQ 根-叶路径最多 1 个 ARCH（禁止 ARCH 嵌套）
```

二期若启用 `fresh_large` 级联模式，条 4 将改为"大需求模式允许嵌套，小需求模式仍禁止"；一期不考虑。

---

## 4. 全局角色体系

### 4.1 设计组（4 角色，每次任务必建）

| 角色 | session 生命周期 | 输入 | 输出 | 反馈对象 |
|---|---|---|---|---|
| `req_decomposer` | 整个任务周期 | 原始需求 + 初始 hints + (critic 反馈) | 整棵 REQ 树（含叶 REQ 验收条件） | — |
| `req_completeness_critic` | 整个任务周期 | REQ 树 + 原始需求 | 完整性报告（缺失点列表） | 回 `req_decomposer` |
| `arch_designer` | 整个任务周期 | REQ 树 + hints + (critic 反馈) | **一次性**产出所有 ARCH.design_content + CODE/TEST 清单 | — |
| `arch_coverage_critic` | 整个任务周期 | 设计产出 + REQ 树 | 覆盖度报告（未覆盖叶 REQ 列表 + 建议） | 回 `arch_designer` |

**battle 收敛条件**（两对都适用，常量 `DEFAULT_MAX_ROUNDS = 5`，写在 `domain/constants.py`，**不暴露到 Task 配置**）：
- critic 输出 `[CONVERGED]` 机读标记（主判据，agent 自判无新问题时主动产出）；
- 或系统自检：critic 连续 2 轮提出的问题列表文本哈希完全一致（视为"无新问题"的隐式收敛）；
- 或达到 5 轮上限（硬性截断）；
- 满足任一则进入 HITL 阀门。

**HITL 可继续推动**：用户在阀门处看到双方最终论断后，若认为还没打磨到位，可用 `continue_battle` 再追加任意轮数，**无上限**。追加后再次停在同一阀门等用户二次审阅。

### 4.2 执行职责（一期并入设计组，不新增角色）

一期**固定用 inherit 模式**：CODE / TEST 的实施工作由 `arch_designer` 本人承担，对应的实施层覆盖校验由 `arch_coverage_critic` 本人承担——两者都是**携带设计期 session 记忆下凡**（通过 adapter 的 session resume 能力）。

因此：
- 一期**只有 4 个全局角色**（即 4.1 表的四位），不存在独立的 `arch_executor` / `impl_coverage_critic`
- 所有执行阶段的调用都是对 `arch_designer` / `arch_coverage_critic` 的再一次 `run()`，通过 `ResumeContext` 续跑其设计期会话
- 二期若启用 `fresh_small` / `fresh_large` 模式，再引入 `arch_executor` + `impl_coverage_critic` 两个执行角色（使用空白上下文 / 每 ARCH 独立 pair）

### 4.3 角色到 adapter 的映射

每个角色都通过 `CodingAgentAdapter` 协议跑。**一期仅支持 `TraeAgentAdapter` 一种 adapter**；所有角色统一绑定到它。仓库 ship 默认 `RoleConfig`：

```yaml
req_decomposer:             { adapter: trae }   # battle 轮数由全局常量控制（5 轮）
req_completeness_critic:    { adapter: trae }
arch_designer:              { adapter: trae }   # inherit 执行阶段通过 prompt injection 续记忆（见 4.5.4 + 5.x）
arch_coverage_critic:       { adapter: trae }
# 二期新增 adapter 后，用户可逐角色覆写；二期新增 arch_executor / impl_coverage_critic 则随 fresh 模式引入
```

**一期**：所有角色的 adapter 固定 `trae`（`TraeAgentAdapter` 目前 `supports_session_resume=false`，记忆策略走 prompt injection）。前端 `TaskConfigDialog` 的 adapter 下拉只有一项，用户无需选择；内部仍走标准的"用户覆写 → workspace 覆写 → ship 默认"三级优先级（只是一期默认即唯一值）。

**二期**：当接入新 adapter 时（如 ClaudeCodeAdapter），前端下拉自动多出一项，`TaskConfigDialog` 按 `AdapterCapabilities` 做细化过滤（比如对 `arch_designer` 只允许选 `supports_session_resume=true` 的 adapter 以启用 native resume）。**orchestrator / PromptComposer / DispatchLoop 的代码一行都不改**——这是契约解耦的价值所在。

### 4.3.2 TraeAgentAdapter 默认 config 含 Playwright MCP + user-data-dir 约定

`TraeAgentAdapter` 一期 ship **一份默认 `trae_config.yaml`**（路径：仓库内 `config/trae_default.yaml`），orchestrator 在 `send()` 时传给 trae-agent 作为启动配置。关键点：

1. **启用 Playwright MCP**：`mcp_servers.playwright` 预配置使用 `npx @playwright/mcp@latest`，并在 `allow_mcp_servers` 列入；`--browser` 选 `chrome`，`--user-data-dir` 指向**全局共享 profile 目录**（默认 `~/.orch/browser-profiles/default/`；可由 `ORCH_BROWSER_PROFILE_DIR` 覆写）。
2. **目的**：让所有 4 个角色都具备"通过本地已登录浏览器访问外部文档（飞书/Notion/Confluence 等）"的能力；利用 `--user-data-dir` 持久化登录态，首次需由用户手工登录一次（详见 A.0）。
3. **首启引导**：orchestrator 启动时调 `_ensure_playwright_profile()` 预检 profile 目录是否存在；不存在 → 自动创建空目录，并在日志 + API 响应里提示"首次使用请在浏览器里登录你需要访问的文档站"。
4. **三级 config 优先级**（与 `RoleConfig` 同构）：用户创建任务时传入 `role_config_override.trae_config_path` → `<workspace>/.orch/trae_config.yaml` → 仓库 ship 默认 `config/trae_default.yaml`。
5. **不关心登录凭据**：orchestrator 不读 Cookie / Token；所有认证态落在 profile 目录，由 Chromium 管。
6. **跨任务共享 profile**：默认所有 Task 共享同一 profile（避免重复登录）；极端隔离需求的用户可在 `role_config_override` 里指定 per-task 的 `user_data_dir`。

### 4.3.1 adapter 无关的记忆策略分路

一期虽然只有 trae，但 PromptComposer 在实现时就按 `AdapterCapabilities.supports_session_resume` 分两路（见 4.5.4 表）：

```
if adapter.capabilities.supports_session_resume:
    TaskSpec.resume_from.artifacts = [role.primary_artifact.identifier]
    prompt = <只拼本轮增量>
else:
    TaskSpec.resume_from.artifacts = []
    prompt = <拼最近 K 轮 Turn.output_text + 本轮任务>   # 一期 trae 走这里
```

这样二期接入支持 native resume 的 adapter 时，**PromptComposer 不用改**，自动切到 native 路径并节省 token。

**三级配置优先级**（高 → 低）：
1. **任务创建时的用户选择**（前端"新建需求任务"弹窗里为每个角色选 adapter，可全盘覆写 ship 默认），写入 `Task.role_config_override`
2. **workspace-level 覆写**（`<workspace>/.orch/role_config.yaml`，如果存在）
3. **仓库 ship 默认**（上表）

任务一旦创建，角色-adapter 绑定锁定到任务生命周期，不支持中途换 adapter（避免跨 adapter session 续跑语义问题）。**adapter 是执行器，角色是职责；职责固定、执行器可换**。

### 4.4 Task 创建流程（零仓库启动）

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Frontend
    participant API as FastAPI
    participant TR as TaskRegistry
    participant NG as NodeGraphStore
    participant DL as DispatchLoop

    U->>FE: 点"新建任务"
    FE->>FE: TaskConfigDialog 收集:<br/>1. title + 根需求文本<br/>2. task_branch（可留空，自动生成）<br/>3. ppe_lane（可选）<br/>4. per-role adapter 覆写（一期仅 trae）
    FE->>API: POST /tasks {config}
    API->>TR: create_task(title, root_req, task_branch?, ppe_lane?, role_overrides?)
    TR->>TR: task_branch 为空则生成 orch/<short_task_id>/<title_slug>
    TR->>NG: INSERT Task 行（无 Repo 记录）
    TR->>TR: mkdir <workspace_path>（空目录）+ mkdir <workspace>/.orch/
    TR->>NG: INSERT 根 REQ 节点（kind=REQ，description=根需求文本）
    TR->>DL: 启动 Task 专属 DispatchLoop 协程
    DL->>DL: Task.status = req_battling<br/>开始 req_decomposer battle
    API-->>FE: 返回 task_id + WebSocket 订阅信息
```

**关键约束**：
- **Task 启动时不 clone 任何仓库**——workspace 目录为空，REQ / ARCH battle 阶段可完全没有代码
- 仓库由 `arch_designer` 在运行期用 `add_repo` op 声明（见 4.4.2），按需 clone
- `task_branch` 在 Task 创建时一次性指定（留空自动生成），所有后续 `add_repo` 声明的仓库都统一用此分支
- AI 所有修改发生在 `task_branch`，不污染 base_branch
- 任务结束后 `task_branch` 保留供用户审阅 / merge；一期不自动 push / PR
- 失败的任务保留 workspace（含半成品）不自动清理

#### 4.4.2 add_repo 运行期 clone 流程

`arch_designer` 在 ARCH 设计 / 执行阶段发现需要访问某仓库时，通过 `<proposed_patch>` 发起 `add_repo` op；`PatchProposalExecutor` 识别后交 `RepoManager.clone_repo()` 同步执行：

```bash
for each add_repo op in a <proposed_patch> from arch_designer:
    validate:
      - turn.role == arch_designer（其他角色发起 → 整批 VALIDATION_ERROR 回滚）
      - git_url 可达
      - name 在本 Task 的 Repos 内未冲突
    cd <workspace_path>
    git clone --branch <base_branch> --single-branch <git_url> <name>
    cd <name>
    git checkout -b <Task.task_branch>                 # 统一分支名
    record git rev-parse HEAD into Repo.base_commit_hash

    # 立刻做一个空 commit 作为"任务起点锚点"；见 4.4.1
    git -c user.name=orchestrator \
        -c user.email=orchestrator@local \
        commit --allow-empty \
        -m "[orch] task start: <task_title>" \
        -m "task_id: <task_id>" \
        -m "repo_added_at: <iso_timestamp>" \
        -m "created_by: <user>" \
        -m "root_requirement: <root_requirement_first_line>"
    record git rev-parse HEAD into Repo.init_commit_hash

    INSERT Repo row (status=ready)
    ack 给 agent（下一轮能 ls 到该目录）
```

**关键行为**：
- **同步阻塞**：agent 当轮 `<proposed_patch>` 提交后，orchestrator 等 clone 完成才 ack 本轮、触发下一轮；clone 过程中 agent 视角"这一轮耗时长"，不需要任何异步感知
- **空 commit 锚点不变**（见 4.4.1）：每个 add_repo 声明的 repo 都走同样的空 commit 流程，保证 CKG 隔离 + git 审计锚点
- **失败回滚**：clone 失败（URL 不通 / 分支不存在 / 权限问题）→ `apply_patch` 整批回滚（其他 ops 都不生效）→ `[VALIDATION_ERROR]` 回传 agent，由 agent 决定重试 / 换路线 / 放弃
- **仅 arch_designer 有权**：其他 3 个全局角色发起 add_repo 会在校验阶段被拒（权限语义写在 system_prompt 里，同时 PatchExecutor 做硬守卫）

#### 4.4.1 空 commit 机制的设计意图

这个看似多此一举的空 commit 同时解决**三个**问题，零成本：

| 问题 | 空 commit 如何解决 |
|---|---|
| trae CKG 跨 Task 隔离 | trae 的 `snapshot_hash = "git-clean-<HEAD>"`；空 commit 让每个 Task 的 HEAD 从 clone 瞬间就独一无二 → `.db` 文件名天然分化、`storage_info.json` 无冲突。**零改动 trae，无需 `TRAE_STORAGE_PATH` 环境变量或 HOME 覆写** |
| 任务起点锚点 | 用户 `git log task_branch` 看到清晰的"任务起点"commit（消息里带 task_id / 用户 / 时间 / 根需求首行）；`git diff init_commit_hash..HEAD` 一键看到本 Task 所有 agent 改动 |
| 整任务回滚 | `git reset --hard <base_commit_hash>` 即可丢弃整个任务所有变更（包括空 commit 本身）；或 `git reset --hard <init_commit_hash>` 保留起点、丢弃后续 agent 改动 |

**额外好处**：
- squash merge 时空 commit 自然被吸收，不污染合并后的 master 历史
- 空 commit 的 message 作为"git 侧独立审计"—— 即使 SQLite DB 被误删，用户通过 `git log` 也能定位任务是哪个人、什么时候、为什么发起的
- 跨仓库起点一致性：一个 Task 的多个 repo 都有带同一 task_id 的 init commit，`git log --all --grep="task_id: abc123"` 可跨仓库锁定同一 Task 的所有 init 锚点

**与 trae 的配合不需要任何约定**：trae 对 `git rev-parse HEAD` 的变化自然感知（通过它自己的 `get_git_status_hash`），无需通信。

### 4.5 多 agent 交互原则与 DispatchLoop 中介角色

#### 4.5.1 核心原则

> **agent 之间从不直接对话；DispatchLoop 是唯一中介。**
> 每次 adapter 调用都是独立的 subprocess 完整调用（含启动、运行、退出）；agent 本身没有跨调用记忆；所有"上下文"都是 DispatchLoop 每轮通过 PromptComposer 从 NodeGraphStore 查出来、拼进新 prompt 的。

这解释了三个关键设计：
- 为什么 Turn append-only 审计就足够——每轮 agent 看到的全部信息 = Turn 里的 `prompt_sent`
- 为什么"ARCH battle" 不是并发的——两个 agent 不能同时说话，DispatchLoop 一次只激活一个
- 为什么 adapter 能随意换——agent 之间没有协议绑定，只有 DispatchLoop 知道谁该下一个上场

**第二条核心原则**：
> **所有节点图的修改都由 agent 通过输出 `<proposed_patch>` 完成，orchestrator 自动应用；用户不直接操作节点**。
> agent 的 `output_text` 里可以夹带 XML 形式的 patch，`PatchProposalExecutor` 解析 → validate → 原子应用到 `NodeGraphStore`。失败时自动写 error Turn 回传同一角色的下一轮。用户的控制手段完全收敛到"发消息"这一种——这让前端 UI 极简（纯对话框），也让 agent 的 agency 完整（自己判断何时该动手、何时先讨论）。详见 6.4 / 7.5。

#### 4.5.2 battle 回合（round-based）机制

两对 battle 角色（`req_decomposer` ↔ `req_completeness_critic`、`arch_designer` ↔ `arch_coverage_critic`）严格串行：

```mermaid
sequenceDiagram
    participant DL as DispatchLoop
    participant PC as PromptComposer
    participant A as Producer<br/>(decomposer / designer)
    participant C as Critic<br/>(completeness / coverage)
    participant NG as NodeGraphStore

    loop round_i ∈ [1, DEFAULT_MAX_ROUNDS=5]
        Note over DL: 生产者轮
        DL->>NG: 查当前产物 + 上一轮 critic 反馈 (round_1 时为空)
        DL->>PC: compose_prompt(role=A, ctx=...)
        PC-->>DL: 完整 prompt
        DL->>A: adapter.run(TaskSpec{instruction=prompt, resume_from=A_session})
        A-->>DL: RunResult(output_text)
        DL->>NG: INSERT Turn(role=A)
        DL->>DL: 解析 output 里 <patch> 应用到图

        Note over DL: 校验者轮
        DL->>NG: 查最新产物
        DL->>PC: compose_prompt(role=C, ctx=最新产物)
        PC-->>DL: 完整 prompt
        DL->>C: adapter.run(TaskSpec{...})
        C-->>DL: RunResult(report)
        DL->>NG: INSERT Turn(role=C)

        alt critic 输出 [CONVERGED]  或  两轮问题列表哈希一致  或  round_i == 5
            Note over DL: 收敛，进入 HITL Gate
        end
    end
```

#### 4.5.3 一个具体 prompt 拼装例（round_2 的 arch_designer prompt）

```
[SYSTEM]
你是 arch_designer 角色。职责：读 REQ 树 + hints，产整棵 ARCH + CODE + TEST 设计。
输出格式：<proposed_arch_tree>...</proposed_arch_tree>

[TASK CONTEXT]
根需求：给登录加速率限制
REQ 树（Gate 1 通过版）：
  REQ-0: ... / REQ-1: 限流算法 / REQ-2: 接入 login / REQ-3: 观测与降级

[你上一轮（round_1）的产出]
<proposed_arch_tree>
  ARCH-0:
    design_content: "redis + token bucket 中间件"
    managed_code_nodes: [C1: RateLimiter, C2: Middleware]
    managed_test_nodes: [T1-unit, T2-unit, T_integration]
</proposed_arch_tree>

[arch_coverage_critic 在 round_1 的反馈]
❌ REQ-3 (观测与降级) 没有对应的 CODE/TEST
⚠ redis 不可用时的降级路径未在 design_content 中说明

[本轮任务]
请基于 critic 反馈修订 ARCH 树。
```

round_1 时 "你上一轮的产出" 和 "critic 反馈" 两段都不拼。

#### 4.5.4 两种记忆传递方式（capability flag 驱动）

| adapter 支持 resume | 实现方式 | 一期使用 |
|---|---|---|
| **是**（capability: `supports_session_resume=true`，如未来的 claude code `--session-id`） | 把 `role.primary_artifact.identifier` 作为 `TaskSpec.resume_from.artifacts` 传给 CLI；CLI 自己从持久化 session 加载完整历史；PromptComposer 只拼**增量**（本轮 critic 的新反馈 / 本轮 CODE 要求） | 二期接入支持的 adapter 后自动启用 |
| **否**（capability: `supports_session_resume=false`，如 trae 当前） | PromptComposer 把最近 K 轮 Turn 的 `output_text` + 当前节点上下文全量拼进 prompt；adapter 每次冷启动，记忆全靠 prompt 文本重建；K 可在 `RoleConfig` 配置，默认 5 | **一期所有角色都走这条** |

**关键设计**：这两种记忆方式对 orchestrator 的**上层逻辑**（DispatchLoop / 5 节的执行流水线 / 6.5 的 REQ 回流续跑）完全透明——上层只下发 `TaskSpec`，PromptComposer 根据 adapter 的 `AdapterCapabilities.supports_session_resume` 自动决定是"传 artifact 索引"还是"拼历史文本"。一期 trae 走第二行、二期 claude 接入走第一行，代码路径合二为一，没有分支语句散在各层。

#### 4.5.5 系统里的所有交互形式总览

| 场景 | 交互形式 | 参与者 | 介质 |
|---|---|---|---|
| REQ 拆分 battle | 回合制互评，N 轮 | req_decomposer ↔ req_completeness_critic | DispatchLoop 拼 prompt 传递 |
| ARCH 设计 battle | 回合制互评，N 轮 | arch_designer ↔ arch_coverage_critic | 同上 |
| converse 对话 | 1:1 人机 | 用户 ↔ 4 角色之一 | DispatchLoop 注入；AI 输出 patch 后自动应用（原子 + 失败回传 error 自修正）；用户无勾选步骤 |
| 执行（inherit，一期唯一模式） | 单 agent 连续调用 | arch_designer 本人按 CODE 逐个 dispatch；arch_coverage_critic 本人按 TEST 校验 | adapter session resume |
| 失败 HITL | 1:1 人机 | 用户 ↔ DispatchLoop | REST + WS |
| continue_battle | 用户触发 + 回合制 | 两个 battle 角色（同 round 机制） | DispatchLoop 追加 N 轮，然后重新等 HITL |

**系统里不存在的交互模式**（为避免误解显式声明）：
- agent 之间的**并发实时对话**（没有两个 subprocess 同时运行且互相发消息）
- agent **同时写 workspace**（全局 `cross_arch: global_serial`）
- agent 通过 **tool-calling 调用另一个 agent**（tool 调用全发生在 adapter 内部，不出 adapter 边界）

---

## 5. 执行阶段（一期固定 inherit 模式）

### 5.1 核心决策

一期**不暴露模式选择**——所有任务默认走 **inherit 模式**：Gate 2 通过后，`arch_designer` 和 `arch_coverage_critic` 继续承担 CODE/TEST 落地，"设计期记忆"由 PromptComposer 拼给它们（见 4.5.4）。理由：
- 省去 ModeSelector / TaskConfigDialog 的模式选项 UI
- 省去执行组两个额外的全局角色（`arch_executor` / `impl_coverage_critic`），角色总数从 6 降到 4
- 设计记忆天然贯穿实施阶段，用户很少再为"CODE 背景不清楚"做 hint 补丁
- 所有 ARCH 同路径唯一（3.1.7 硬约束），"单 agent + 单 session 上下文"足够容纳

**一期 inherit 的"记忆载体"**：因唯一 adapter `TraeAgentAdapter` 的 `supports_session_resume=false`，记忆**不是**通过 native session 续跑，而是**每次新 subprocess + PromptComposer 拼最近 K 轮 Turn 历史（默认 K=5）+ 当前 ARCH.design_content + 当前 CODE/TEST 要求**。从 agent 视角看，每次都是"冷启动但 prompt 里有完整上下文"；从架构视角看，这与二期接入 native-resume adapter 的行为等价（只是 token 成本更高）。**这层差异对上层完全透明**——上层只管调 `adapter.run(TaskSpec)`。

### 5.2 执行时序

```mermaid
sequenceDiagram
    participant DL as DispatchLoop
    participant AD as arch_designer session
    participant ACC as arch_coverage_critic session
    participant NG as NodeGraphStore

    Note over AD,ACC: 设计阶段已完成<br/>两个 session 保留完整记忆
    loop 每个 ARCH 节点（按依赖拓扑序，严格串行）
        loop 每个 CODE_i ∈ ARCH.managed_code_nodes
            DL->>AD: run(TaskSpec{node=CODE_i, resume_from=[AD.primary_artifact]})
            AD-->>NG: 写 CODE_i 的 Turn（role_name=arch_designer）
        end
        loop 每个 TEST_i ∈ ARCH.managed_test_nodes
            DL->>AD: run(TaskSpec{node=TEST_i, resume_from=[AD.primary_artifact]})
            AD-->>NG: 写 TEST_i 的 Turn
        end
    end
    DL->>ACC: run(TaskSpec{instruction=整体实施校验, resume_from=[ACC.primary_artifact]})
    ACC-->>NG: 写校验 Turn（含 coverage report）
    alt coverage report 非空
        DL->>AD: run(instruction=补充实施 + 上条报告)
        Note over DL: 补 → 再校验，循环至 report 为空或触发失败 HITL
    end
```

### 5.3 要点与约束

- **CODE/TEST 的 dispatch** 本质是对 `arch_designer` 再调一次 `run(TaskSpec)`；记忆如何传递由 PromptComposer 按 adapter capability 决定（见 4.5.4）：
  - 一期 trae：冷启动 + prompt 拼最近 K 轮历史 + 本节点上下文
  - 二期 native-resume adapter：传 artifact 索引，prompt 只拼增量
- **adapter 无硬约束**：不要求 `supports_session_resume=true`（一期 trae 就不支持，走 prompt injection 同样可行）
- **严格串行**：一个 CODE 跑完、它的 TEST 跑完，才轮下一个 CODE；跨 ARCH 也严格顺序（topo 顺序按 `depends_on` 边）
- **Token 成本提示**：一期 prompt injection 每次带最近 K 轮历史，成本较高；大需求 / 长任务建议二期接入 native-resume adapter 或启用 `fresh_small` 模式分摊
- **失败处理**：单 CODE / TEST 失败 → halt 全系统 → HITL 三选一（re-dispatch / skip / 打回 arch_designer 改方案回 Gate 2 前）

> **二期升级位**：
> - `fresh_small`：新增 `arch_executor` + `impl_coverage_critic` 两个全局空白 session 角色，适合设计产物自解释、希望执行"忘掉"设计纠结的场景
> - `fresh_large`：每 ARCH 独立 `(executor, critic)` pair；允许 ARCH 嵌套；子 ARCH 结果上浮到祖先 ARCH；适合单上下文放不下的超大需求
> 一期不实现。

---

## 6. HITL 双阀门

### 6.1 阀门设计

| 阀门 | 时机 | 审的是 | 可执行动作 |
|---|---|---|---|
| **Gate 1** | `req_decomposer`+`completeness_critic` 收敛后 | 整棵 REQ 树 + completeness 报告 | approve / reject_with_comment / approve_partial / continue_battle |
| **Gate 2** | `arch_designer`+`coverage_critic` 收敛后 | 整棵 ARCH 树（design_content + managed CODE/TEST 清单）+ coverage 报告 | approve / reject_with_comment / approve_partial / continue_battle |

**Gate 2 发现 REQ 本身不完整的轻量退路**（一期支持）：用户不必放弃任务重起，而是在对话面板里选 `req_decomposer` 或 `req_completeness_critic` 作为对话对象，发起一段 converse 说明缺口；被唤醒的 REQ 角色以增量方式补充 REQ 树（自动应用 patch）。新增的 REQ 会触发 orchestrator 把"REQ 增量清单"作为 user input 喂回 `arch_designer` 下一轮 prompt，`arch_designer` 自主决定"扩展现有 ARCH"还是"新增 ARCH 节点"，之后 ARCH battle 继续走到 Gate 2 重审。详见 6.5。

**注意**：Gate 1 **不会重开**——用户发起这次 converse 即视作对增量的隐式 approve，审计靠 Turn 链追溯；不做全量回滚或 Gate 1 重审（那属于跨阀门完整退回，仍留二期）。

### 6.2 `approve_partial` 的语义与 UI

**UI 交互**：前端树上**每个节点旁显示一个 approve/reject 切换按钮**；用户**逐节点**勾选决议（不支持"只勾打回的其余默认通过"式偷懒，避免漏审）。所有节点决议完后点"提交"按钮成为一次 `HitlDecision`。

`payload` 结构：

```
approve_partial.payload = {
  approved: list[node_id],
  rejected: list[{ node_id, comment }]
}
```

UI 约束：提交前前端校验 `approved ∪ rejected` 必须等于 Gate 上所有展示节点（不允许空着）。

Orchestrator 行为：
- Gate 1 `approve_partial` → `req_decomposer` 以 `rejected[].comment` 为 hint 重拆**被打回的子树**，其它子树不动
- Gate 2 `approve_partial` → `arch_designer` 仅重新设计被打回 ARCH 的子树；其它 ARCH 直接进入 `dispatching`

这比 707fc8c5 的 4 模式 HITL 省去 `inline_edit` 和 `accept_coverage_fix` 两种，但靠 `approve_partial` 的 per-node 决议 + 评论文本覆盖了大部分使用场景。

### 6.3 `continue_battle` 的语义

用户看过 battle 双方的最终论断后，可能觉得 critic 还有挑不出的问题、或 designer 还能更细化；此时点 "再战 N 轮" 按钮：

```
continue_battle.payload = { extra_rounds: int, comment: str | null }
```

Orchestrator 行为：
- 在 `ancestor_hints` 之外**追加**用户评论（如有）作为 must-weight hint
- 该对 battle 继续跑 `extra_rounds` 轮，跑完后重新停在同一阀门等用户审
- **无上限**：理论上用户可以无限"再战"；orchestrator 只做轮次记录不阻止
- 前端 UI 每次展示当前轮数和历次双方论断演化轨迹，便于用户判断是否真有进展

### 6.3 节点级 HITL（执行阶段）

执行阶段不再有节点级"方案审批"（方案在 Gate 2 已统一审过）；仅保留**失败后 HITL**：

```
CODE/TEST 失败 → halt 全系统 → 前端弹窗
用户选：re-dispatch / skip / 打回 arch_designer 改方案（回到 Gate 2 前）
```

### 6.4 节点引用对话（converse）

**背景与定位**：思维导图本身是只读的——用户不能在图上增删节点、拖拽、改 hint、改 description。所有修改都通过"和角色对话"来表达："你漏掉了这条 REQ"、"这个 CODE 的签名要改成 async"。对话支持精确引用图上任意节点作为上下文。

**核心原则**：用户**不能直接操作节点**（不能勾选 patch、不能拖拽、不能点加/删按钮）。**所有节点修改由 agent 通过输出 `<proposed_patch>` 自主完成，orchestrator 自动应用**。用户通过自然语言对话向 agent 施加影响；不满意就继续对话让 agent 再改。这样做的好处：前端 UI 极简、agent 的 agency 完整、所有修改全量审计可回溯。

#### 6.4.1 前端布局

```mermaid
flowchart LR
    MM["思维导图<br/>(只读，实时反映 agent 改动)"]
    CP["对话面板<br/>(侧栏常驻)"]
    SEL["对话对象下拉<br/>(4 角色，按阶段过滤)"]
    IN["输入框<br/>@触发节点选择器"]
    HIS["对话历史<br/>(自然语言 + 已应用变更 badge)"]

    MM -- "右键节点 → 在对话中引用" --> CP
    CP --> SEL
    CP --> HIS
    CP --> IN
```

**对话对象下拉**按当前任务阶段过滤可用角色：

| 阶段 | 可对话角色 |
|---|---|
| REQ battle 运行 / Gate 1 等待 | req_decomposer, req_completeness_critic |
| ARCH battle 运行 / Gate 2 等待 | arch_designer, arch_coverage_critic **+ req_decomposer, req_completeness_critic**（后两者用于"发现 REQ 不完整时的轻量增量修订"，见 6.5） |
| 执行阶段（inherit） | arch_designer, arch_coverage_critic |
| 失败 halt | 当前阶段的角色 + 可回溯更早阶段的角色（如到 arch_designer 改方案） |

**为什么只在 Gate 2 等待态开放 REQ 角色回流**：ARCH battle 进行中唤醒 REQ 角色会让 `arch_designer` 的上下文"脚底下动"（他还在写当前这轮 output），系统一致性难保证。因此一期约定**仅 Gate 2 等待态可选 REQ 角色作为对话对象**；ARCH battle 进行中的 converse 下拉里看不到 REQ 角色。用户若在 battle 跑中想排队补 REQ，可以等 battle 自然收敛到 Gate 2 等待态（秒级到分钟级）再发起——用 6.4.5 的正常排队语义即可。

#### 6.4.2 节点引用的两种输入方式

**方式 A：输入框 `@` 触发**
- 键入 `@` → 弹出节点选择器（可按 title / id / kind 搜索）
- 选中 → 插入 chip，展示 title 与 kind 图标，hover 显示 breadcrumb：`REQ > REQ-限流 > REQ-异常情况 (id=req_37)`
- 一条消息可插多个 chip，自由夹杂在自然语言中

**方式 B：思维导图右键**
- 右键任一节点 → 菜单项"在与 <role> 的对话中引用此节点"
- 自动切到对话面板 + 输入框插入 chip + 光标停在其后

#### 6.4.3 引用 → Prompt 展开

**前端提交的消息**（举例）：
```
你好像漏掉了 [REQ-登录限流-异常情况] 这条 REQ 在 [ARCH-0] 方案里的补充；
另外 [CODE-rate_limiter] 的签名应该改成 async
```

**Orchestrator 拼给 adapter 的 prompt**：
```
[USER_MESSAGE]
你好像漏掉了 <<ref_0>> 这条 REQ 在 <<ref_1>> 方案里的补充；
另外 <<ref_2>> 的签名应该改成 async
[END_USER_MESSAGE]

[REFERENCED_NODES]
<<ref_0>>
  id: req_37
  kind: REQ
  breadcrumb: REQ-0 > REQ-登录限流 > REQ-异常情况
  title: "redis 不可用时降级行为"
  description: "..."
  hints: [...（结构化 NodeHint 展开）]
  status: done
<<ref_1>>
  id: arch_0
  kind: ARCH
  design_content: "..."
  managed_code_nodes: [code_1, code_2, code_3]
  ...
<<ref_2>>
  id: code_1
  kind: CODE
  title: rate_limiter
  description: "实现 token bucket 算法的 RateLimiter 类"
  ...
[END_REFERENCED_NODES]
```

AI 精确知道用户在说哪些节点，不靠自然语言匹配。

#### 6.4.4 AI 回复 → `<proposed_patch>` → 自动应用

**AI 响应约定**：在自然语言回复之外，用 XML 包裹结构化 patch：

```xml
<proposed_patch>
  - op: add_node
    parent_id: arch_0
    kind: CODE
    title: circuit_breaker
    description: 当 redis 连续失败 3 次时熔断 60 秒
    hints:
      - { category: code_pointer, weight: must, content: "middleware/breaker.py" }
    satisfies: [req_37]
  - op: modify_node
    node_id: code_1
    fields:
      description: "async def rate_limit(request) -> bool ..."
  - op: modify_node
    node_id: arch_0
    fields:
      design_content_append: "<追加熔断章节文本>"
</proposed_patch>
```

**自动应用流程**（无用户勾选环节）：

```mermaid
flowchart TD
    A["AI 产出 output_text<br/>(含 &lt;proposed_patch&gt;)"] --> B["PatchProposalExecutor<br/>解析 XML → ops 列表"]
    B --> C{"NodeGraphStore<br/>validate()"}
    C -- "全部合法" --> D["应用 ops<br/>写入节点图"]
    D --> E["WS 推送图更新<br/>+ 对话面板显示<br/>'已应用 N 处变更' badge"]
    C -- "任一 op 违规" --> F["整个 patch 回滚<br/>(原子性：要么全应用要么全拒绝)"]
    F --> G["写 error Turn<br/>(adapter_name=orchestrator)<br/>payload=违规详情"]
    G --> H["下一轮自动把 error Turn<br/>作为 user input 回传给同一角色"]
    H --> I["角色自修正后重新输出 patch"]
```

**原子性**：一条消息里的多条 ops 走"全成功或全回滚"。任一 op 违反图硬约束（3.1.7）或引用了不存在的 node_id，整个 patch 被拒绝。

**system_prompt 要求**：每个角色的 system_prompt 必须明确告知 —— "你输出的 `<proposed_patch>` 会被**立即**应用到节点图，不经过用户确认；请谨慎输出、必要时先用自然语言讨论再改"。这引导 agent 自己判断"何时先讨论 vs 何时直接动手"，对齐用户赋予 agent 完整 agency 的设计意图。

**用户的控制手段**（回到对话本身）：
- 看到图变化不对 → 继续对话："把刚才加的 circuit_breaker 删了，换一种"
- 不想 agent 动手先讨论 → 在消息里明确："先不要改图，我们讨论一下方案"
- agent 连续输出低质量 patch → 走 Gate 1/2 的 `reject_with_comment` / `continue_battle`（这些仍然是阀门决议，不是节点操作）

支持的 patch op 类型（一期）：

| op | 作用 | 校验规则 |
|---|---|---|
| `add_node` | 新增节点 | 校验 parent 存在 + 图结构硬约束（3.1.7） |
| `modify_node` | 改节点字段（title / description / hints / design_content_append） | **不允许改 status**；status 只能由 DispatchLoop 按生命周期转 |
| `delete_node` | 删节点 | 仅 pending / design_pending 状态允许删；已执行过的节点只能用 `modify_node` 改 status 到 deprecated（沿用上条规则的例外：deprecated 是唯一允许 agent 改的 status） |
| `add_edge` | 新增虚边（satisfies / covers / depends_on） | 不能引入环（depends_on） |
| `remove_edge` | 删虚边 | 不能删 parent_of |
| `add_repo` | 声明新代码仓库 | **仅 `arch_designer` 角色有权发起**（其他角色发起 → `[VALIDATION_ERROR]` 整批回滚）；字段：`git_url` + `name`（workspace 下的目录名，Task 内不能重名）+ `base_branch`；执行时机：**同步阻塞**（orchestrator 等 `RepoManager.clone_repo()` 完成才 ack 本轮）；失败 → 整批回滚 + 回传 agent 自修正 |

**边界：不允许的 op**（一期硬禁）：
- 修改 Task 配置（execution_mode / role_config_override / task_branch / ppe_lane）—— 由 Task 创建时决定，agent 无权改
- **删除 Repo**（`remove_repo` 留二期）—— 一旦 `add_repo` 声明，仓库在任务生命周期内存在
- 修改他人角色的 hints.weight=must 的内容 —— 避免 agent 互相覆盖关键上下文（可加 must 的新 hint，不能改/删别的角色留的 must hint）

#### 6.4.5 对话时机与中断语义（一期：**任意时刻可发起 + 排队**）

| 系统当前状态 | 用户发起对话 | 系统行为 |
|---|---|---|
| 空闲（Gate 等待 / 全部 done） | → | 立即处理，直接调 adapter |
| battle 某一轮正在跑 | → | 消息**排队**；本轮 battle 结束后处理；处理时作为下一轮的额外 user input |
| 执行阶段某节点 dispatch 中 | → | 消息排队；本节点 dispatch 结束后、进入下一节点前处理 |
| 失败 halt | → | 立即处理 |

**一期显式放弃"立即中断"**：
- 中断正在跑的 adapter subprocess 会造成 workspace 半成品（文件只写一半）
- 风险大于收益；用户真的急可以等当前节点完成（通常几秒到几分钟）
- 二期可选升级位，配套 `GitCheckpointer` 的回滚能力

#### 6.4.6 对话存储：只用 Turn，不扩大节点图

**关键决策**：对话轮**不生成 DISCUSSION 节点**，只作为 `Turn` 存储。

每次对话（用户一条 + AI 一条）产生 2 条 Turn，挂到"被对话角色"的 `memory_artifacts` 链上：

```
Turn_user {
  role_name: <target_role>
  adapter_name: "human"
  output_text: <用户消息 markdown，含 chip>
  consumed_artifacts: [target_role.primary_artifact]  // 接上该角色 session
  produced_artifacts: []                              // 人工 Turn 不产新句柄
  payload_extra: { referenced_node_ids: [req_37, arch_0, code_1] }
}
Turn_ai {
  role_name: <target_role>
  adapter_name: <该角色绑定的 adapter>
  prompt_sent: <6.4.3 的完整展开 prompt>
  output_text: <AI 回复，含 <proposed_patch>>
  consumed_artifacts: [target_role.primary_artifact + Turn_user 的概念]
  produced_artifacts: [<新 session 句柄，若 adapter 产生>]
  payload_extra: {
    applied_patch_summary: {                // 记录本轮 patch 被自动应用的情况（见 6.4.4）
      op_count: int,
      ops_digest: [ { op, target_id, ok: bool } ],
      validation_error: str | null         // 若 patch 被整体回滚，这里是错误原因
    }
  }
}
```

**反向索引**：前端查看某节点的 Turn 面板时，可以看到"本节点在对话中被引用过 N 次"的提示，点进去跳到对应对话轮。实现：`NodeGraphStore` 给 `Turn.payload_extra.referenced_node_ids` 建二级索引即可。

**审计完整性**：任一节点的"演化历史"可通过其 `turns` 链 + 反向对话索引 100% 重建——看到某个 CODE 节点从哪个对话轮被创建、哪几次对话里被修改过、每次改了什么字段。这是补偿"用户无法直接操作节点"的关键——所有 agent 改动都有完整溯源。

### 6.5 Gate 2 处 REQ 增量修订（轻量跨阀门）

**场景**：用户在 Gate 2 审 ARCH 方案时，突然意识到"这不是 ARCH 设计得不好，是 REQ 树漏了某一条细节需求"。一期允许用户**不重起任务**，直接在对话里唤醒 REQ 两角色补增量。

#### 6.5.1 流程

```mermaid
flowchart TD
    GATE2["Gate 2 等待态<br/>(ARCH battle 已收敛)"] --> CHOICE{"用户判断"}
    CHOICE -- "ARCH 方案本身不够" --> RJ["reject_with_comment<br/>或 approve_partial<br/>(arch_designer 重跑)"]
    CHOICE -- "REQ 树有缺口" --> CV["对话面板选 req_decomposer<br/>或 req_completeness_critic<br/>发起 converse"]
    CV --> RM["被唤醒角色的 mini-battle<br/>(最多 DEFAULT_MAX_ROUNDS=5 轮<br/>或 [CONVERGED] / 隐式收敛)"]
    RM --> PATCH["产出 REQ patch<br/>(add_node / modify_node)"]
    PATCH --> APPLY["PatchProposalExecutor<br/>原子应用到节点图"]
    APPLY --> WATCH["REQ 树变更 watcher 触发<br/>(见 6.5.3)"]
    WATCH --> ADR["arch_designer 续跑<br/>(带 'REQ 增量清单' 作为 user input)"]
    ADR --> ACC["arch_coverage_critic 跟进<br/>正常 ARCH battle 收敛"]
    ACC --> GATE2B["回到 Gate 2 等待态<br/>(树已更新，用户再审)"]
    GATE2B -.循环可无限发起.-> CHOICE
```

#### 6.5.2 不重开 Gate 1 的依据

- 用户发起"唤醒 REQ 角色"的 converse 本身即是对增量补充的**隐式 approve**——语义上比 Gate 1 重审更精确（Gate 1 要审整棵树，这里只补增量）
- 增量 REQ 的审计通过 Turn 链完整保留：可追溯是哪条用户消息触发、哪个角色输出了 patch、哪些 REQ 节点被新增
- 如果用户后悔，可以继续发 converse 让 REQ 角色撤回（`modify_node` 改 status 为 deprecated 或 `delete_node` 如果还没被 ARCH 覆盖）

#### 6.5.3 REQ 变更 watcher（后端触发 ARCH 续跑）

`PatchProposalExecutor` 应用 ops 后，若满足所有下列条件：
1. 任务当前阶段是 `arch_battle_await_gate2`（Gate 2 等待态）
2. 本次 ops 中包含对 REQ 节点的 `add_node` / `modify_node(fields 涉及 description/hints)` / `delete_node`
3. 本次 ops 由 `req_decomposer` 或 `req_completeness_critic` 产出（`adapter_name` + `role_name` 判断）

则 watcher 自动：
- 把"REQ 增量摘要"写成一条 must-weight hint 追加到根 REQ 节点的 `hints`（供后续审计追溯）
- 将任务阶段从 `arch_battle_await_gate2` 切回 `arch_battle_running`
- enqueue 一轮 `arch_designer` 调用，`user_input` 是 `REQ 增量清单 + 上一次 coverage report`
- 之后按正常 ARCH battle 流程（arch_designer ↔ arch_coverage_critic）直到再次收敛到 Gate 2

**关键设计**：`arch_designer` 续跑而不是从头开始——记忆由 PromptComposer 按 adapter capability 自动恢复（一期 trae 走 prompt injection，二期 native-resume adapter 走 session resume，见 4.5.4），能自主决定是在现有 ARCH 下追加 CODE/TEST、还是新增 ARCH 节点。orchestrator 不强制它如何改（避免把 agent 的 agency 切掉）。

#### 6.5.4 上限与防抖

- mini-battle 沿用全局常量 `DEFAULT_MAX_ROUNDS=5`；每次 REQ 回流跑满这个上限或提前收敛（[CONVERGED] / 两轮问题列表哈希一致）
- 用户可以无限次发起回流 converse（和 Gate 2 `continue_battle` 一样无上限，受 adapter 预算自然约束）
- 防抖：同一任务在 `arch_battle_running` 态时，发给 REQ 角色的 converse 仍然**排队**（走 6.4.5 的 ConverseQueue），不并发执行

#### 6.5.5 审计的额外要求

每次 REQ 回流产生的 Turn 在 `payload_extra` 里加一个标记字段 `triggered_from_gate: 2`，便于前端 Turn 面板把"阀门 2 处的 REQ 回流"作为一个分组高亮展示，区别于任务初期的 REQ battle 轮。

---

## 7. 关键数据流

### 7.1 REQ 树产出（设计阶段前半）

```mermaid
sequenceDiagram
    participant U as User
    participant DL as DispatchLoop
    participant RD as req_decomposer
    participant RCC as req_completeness_critic
    participant NG as NodeGraphStore
    participant FE as Frontend

    U->>DL: POST /task {root_requirement, hints}
    loop max 3 rounds or converge
        DL->>RD: run(TaskSpec{instruction=需求+已有树+critic反馈})
        RD-->>DL: RunResult(REQ 树 patch YAML)
        DL->>NG: 写 Turn(RD) + 应用 patch 到节点图
        DL->>RCC: run(TaskSpec{instruction=REQ树})
        RCC-->>DL: RunResult(completeness report)
        DL->>NG: 写 Turn(RCC)
        alt 报告为空
            DL->>DL: break (收敛)
        end
    end
    DL-->>FE: 推送 Gate 1 就绪事件
```

### 7.2 ARCH 树产出（设计阶段后半）

```mermaid
sequenceDiagram
    participant DL as DispatchLoop
    participant AD as arch_designer (session)
    participant ACC as arch_coverage_critic (session)
    participant NG as NodeGraphStore
    participant FE as Frontend

    Note over DL: 从 Gate 1 approve 后开始
    loop max 3 rounds or converge
        DL->>AD: run(TaskSpec{instruction=REQ树+hints+acc反馈, resume_from=AD.primary_artifact})
        AD-->>DL: RunResult(ARCH patch: design_content + managed CODE/TEST 清单)
        DL->>NG: 写 Turn(AD) + 应用 ARCH/CODE/TEST 节点创建/修改
        DL->>ACC: run(TaskSpec{instruction=ARCH树+REQ树, resume_from=ACC.primary_artifact})
        ACC-->>DL: RunResult(coverage report)
        DL->>NG: 写 Turn(ACC)
        alt 报告为空
            DL->>DL: break
        end
    end
    DL-->>FE: 推送 Gate 2 就绪事件（含 CoverageReport 展示）
```

### 7.3 执行阶段（inherit 模式，一期唯一）

```mermaid
sequenceDiagram
    participant DL as DispatchLoop
    participant AD as arch_designer (下凡)
    participant ACC as arch_coverage_critic (下凡)
    participant NG as NodeGraphStore

    Note over DL: Gate 2 approve
    loop 按 ARCH 依赖拓扑，每个 ARCH
        loop 按 ARCH.managed_code_nodes 顺序
            DL->>AD: run(TaskSpec{task_kind=implement, node_id=CODE_i, resume_from=AD session})
            AD-->>DL: CODE 修改完成
            DL->>NG: Turn + CODE status=done
            DL->>AD: run(TaskSpec{task_kind=test, node_id=TEST_i, resume_from=AD session})
            AD-->>DL: TEST 跑完
            DL->>NG: Turn + TEST status=passed/failed
        end
        DL->>NG: ARCH aggregate_status 聚合
    end
    DL->>ACC: run(TaskSpec{task_kind=verify, instruction=全部 CODE/TEST 摘要, resume_from=ACC session})
    ACC-->>DL: 整体校验报告
    DL->>NG: Turn
    alt 报告有缺失
        DL->>AD: 补实施（循环）
    end
```

### 7.4 失败处理（沿用 707fc8c5 5.3 节思路）

参见 707fc8c5 版本的 5.3 节；本版仅补充：**任一 CODE/TEST 失败 → 全系统 halt → HITL 弹窗 → 三选一**（re-dispatch / skip / 打回设计阶段）。

### 7.5 节点引用对话 → patch 自动落地

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Frontend
    participant DL as DispatchLoop
    participant Q as ConverseQueue
    participant R as target_role
    participant PPE as PatchProposalExecutor
    participant NG as NodeGraphStore

    U->>FE: 输入消息 + @chip 引用若干节点
    FE->>DL: POST /converse {target_role, message, referenced_node_ids}
    alt 系统空闲
        DL->>R: run(TaskSpec{instruction=拼好的消息+引用节点上下文, resume_from=R.primary_artifact})
    else battle / dispatch 在跑
        DL->>Q: 入队
        Note over Q: 当前轮/节点结束后出队
        Q-->>DL: 出队
        DL->>R: run(TaskSpec{...})
    end
    R-->>DL: RunResult(output_text, 可能含 &lt;proposed_patch&gt;)
    DL->>NG: 写 Turn_user + Turn_ai
    DL->>PPE: 解析并应用 patch
    alt patch 合法
        PPE->>NG: 原子写入 ops + 更新 Turn_ai.payload_extra.applied_patch_summary
        NG-->>FE: WS 推送图更新 + 对话面板 badge
    else patch 违规
        PPE->>NG: 写 error Turn(adapter_name=orchestrator)
        NG-->>DL: 触发下一轮自动 re-run，error 作为 user input 回传 R
        DL->>R: run(TaskSpec{instruction=validation_error, resume_from=...})
        R-->>DL: RunResult(修正后的 patch)
        DL->>PPE: ...（循环直至合法或连续 N 次失败升级到 HITL 提示）
    end
```

**无用户勾选环节**：整个流程用户只输入一条消息，其余由 orchestrator 和 agent 闭环完成；用户看到的是图的实时更新 + 对话面板的自然语言回复 + badge。

### 7.6 Gate 2 处 REQ 增量修订

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Frontend
    participant DL as DispatchLoop
    participant RD as req_decomposer
    participant RCC as req_completeness_critic
    participant PPE as PatchProposalExecutor
    participant WATCH as REQ Watcher
    participant AD as arch_designer
    participant ACC as arch_coverage_critic
    participant NG as NodeGraphStore

    Note over FE: Gate 2 等待态
    U->>FE: 对话选 req_decomposer + 消息"漏了 XXX 这条 REQ"
    FE->>DL: POST /converse {target_role=req_decomposer, ...}
    DL->>RD: run(TaskSpec{resume_from=RD.primary_artifact, user_input})
    RD-->>DL: RunResult(output_text, 含 REQ patch)
    DL->>PPE: 应用 patch
    PPE->>NG: 写入 REQ 新节点 + Turn_ai(triggered_from_gate=2)
    PPE-->>WATCH: 通知"REQ 增量 + 当前阶段=await_gate2"
    WATCH->>DL: 任务阶段 await_gate2 → arch_battle_running; enqueue arch_designer
    DL->>RCC: 并行触发 completeness check（可选，一期也做）
    RCC-->>DL: 若仍有缺口 → loop 回 RD；若无缺口 → 继续

    loop ARCH battle 续跑至收敛
        DL->>AD: run(instruction=REQ 增量清单 + 上轮 coverage report)
        AD-->>DL: RunResult(ARCH patch：扩展现有 ARCH / 新增 ARCH)
        DL->>PPE: 应用 patch
        DL->>ACC: run(instruction=更新后的 ARCH 树)
        ACC-->>DL: coverage report
        alt report 为空
            DL->>DL: 收敛
        end
    end
    DL-->>FE: 推送 Gate 2 重新就绪事件
    Note over FE: 用户再审，满意就 approve / 否则继续发 converse 或 reject
```

**两个可选增强（一期可选实现）**：
1. REQ 增量后自动跑一次 `req_completeness_critic` 小 battle，确保增量本身也不留新缺口（图里的 RCC 分支）
2. 如果 watcher 在短时间（如 30s）内被多次 REQ patch 触发，合并成一次 arch_designer 续跑（防抖）

---

## 8. CodingAgentAdapter 契约（完全沿用 707fc8c5，一期解耦基石）

`AdapterCapabilities / TaskSpec / ResumeContext / AgentEvent / RunResult / 协议方法`**无改动**。见 707fc8c5 版本第 4 节。

本版关键调整：

- **去除了"特定角色必须 `supports_session_resume=true`"的硬约束**——一期 trae 不支持 resume，但通过 PromptComposer 的 prompt injection 路径等价实现 inherit 模式（见 4.5.4）。orchestrator 上层代码一字不改地适配未来支持 native resume 的 adapter
- 角色到 adapter 的映射 `RoleConfig` 允许前端覆写（一期只有 trae，下拉只一项；二期多 adapter 时自动丰富）

### 8.1 一期扩展点 checklist

以下是"给二期加一个新 adapter（如 ClaudeCodeAdapter）"需要改的所有文件清单：

| 文件 | 改动 |
|---|---|
| `adapters/claude_code_adapter.py` | **新建**：实现 `CodingAgentAdapter` 协议的 5 个方法 + 声明 `AdapterCapabilities` |
| `adapters/__init__.py` | **1 行**：`AdapterRegistry.register("claude_code", ClaudeCodeAdapter)` |
| `role_config.yaml`（可选） | **默认映射覆写**：如把 `arch_designer` 默认改成 claude |
| `TaskConfigDialog`（前端，可选） | **下拉自动多一项**（后端 `GET /adapters` 接口返回所有已注册 adapter）；可选地对特定角色按 capability 过滤 |

**不改**：orchestrator 的 `DispatchLoop` / `PromptComposer` / `RoleAgentRegistry` / `NodeGraphStore` / `PatchProposalExecutor` / `ReqWatcher` / `ConverseQueue` 等**任何一处**。这是"契约解耦"的硬承诺——也是一期 trae-only 实施时就要守住的工程纪律，不允许在 orchestrator 里写 `if isinstance(adapter, TraeAgentAdapter): ...` 这样的分支。

### 8.2 一期 `TraeAgentAdapter` 的要点

| 协议方法 | 一期实现要点 |
|---|---|
| `capabilities()` | `supports_session_resume=false` / `supports_streaming=true`（读 trajectory tail）/ `cwd_is_workspace_root=true` |
| `run(TaskSpec) -> RunResult` | subprocess 调 `trae run <task>` + `--trajectory-file=<path>` + `--working-dir=<workspace>`；task 文本从 `TaskSpec.instruction` 拼（已含 PromptComposer 拼好的历史） |
| `stream_events(run_id)` | 轮询 / tail trajectory 文件，转成 `AgentEvent` 流推给 EventBus |
| `persist_artifact(turn_id)` | 把 trajectory 文件路径登记为 `MemoryArtifactRef(kind="trajectory", identifier=path)` |
| `load_artifact(ref)` | 一期空实现（trae 不支持从 trajectory 续跑；PromptComposer 会读 artifact 路径来拼历史，不走 adapter） |

---

## 9. 对 trae-agent 的依赖（一期唯一 adapter 的落地细节）

完全沿用 707fc8c5 第 6 节：trae-cli subprocess + trajectory 文件两件事。**注意**：这一节是 `TraeAgentAdapter` 的内部实现说明，不是 orchestrator 的依赖——orchestrator 只依赖 `CodingAgentAdapter` Protocol，永远不得直接 import `trae_agent` 包的任何符号。

### 9.1 trae CKG 跨 Task 隔离策略

trae 把 CKG（代码知识图谱）持久化到 `~/.trae-agent/ckg/<snapshot_hash>.db`（全局位置）；物理 `.db` 文件名由 `snapshot_hash = "git-clean-<HEAD>"` 或 `"git-dirty-<HEAD>-<md5(diff)>"` 决定。这意味着**两个不同 Task 对同一代码仓库独立 clone 后，若 HEAD 完全相同、都 clean，会共用同一 `.db` 文件**，可能出现幽灵重建、SQLite 写锁冲突等问题。

**一期通过 "任务起点空 commit" 机制解决**（见 4.4.1）：Task 创建时 `RepoManager` 在每个 repo 的 `task_branch` 上立刻做一个 `git commit --allow-empty`，让 HEAD SHA 从一开始就分化——trae 的 `snapshot_hash` 天然不同，`.db` 文件和 `storage_info.json` 条目各自独立。**零改动 trae，零运行时开销，无需 `TRAE_STORAGE_PATH` / HOME 覆写**。

**附加的 agent 侧约定**（system_prompt 引导，非硬约束）：
- 优先用 `bash grep` / `find` / 文件读取做定位；仅在需要跨函数符号关系分析（如"这个 class 的所有 caller"）时才用 `ckg_tool`
- 目的：降低 CKG 重建频率（agent 每次改代码后 dirty diff 一变，下次 ckg_tool 调用就触发重建——重建代价 = 全目录 AST 解析）
- 这条约定只影响性能，不影响正确性；agent 自主判断即可

### 9.2 trae 冷启动开销画像

| 启动开销项 | 估算 | 一期是否关注 |
|---|---|---|
| Python + import + tools 实例化 | ~1-3s / subprocess | 相对 LLM 调用延迟可忽略 |
| trae `new_task()` message 重置 | 每次都做（trae 设计即如此）；interactive 模式也不续聊 | 与本设计的 PromptComposer prompt injection 天然对齐 |
| CKG 磁盘连接 | ms 级（sqlite3.connect） | 忽略 |
| CKG 全量重建 | 仅首次 / 代码变更后；秒级 → 分钟级（视仓库规模） | **通过 system_prompt 引导 agent 节制使用 ckg_tool 缓解**；不改 trae |
| LLM 服务端 prompt cache | prefix 稳定可命中 | PromptComposer 按"稳定段（system + 工具 + task 定义）→ 动态段（历史 + 本轮指令）"顺序拼 prompt，便于命中 |

**结论**：一期 subprocess 冷启动模式在功能与性能上**与任何可选的"trae 长驻 interactive pipe"方案等价**（trae 自身在跨任务不续聊，"长驻"带不来记忆优势）；仅省 1-3s / 次的 Python 启动开销，相对 LLM 延迟可忽略。选 subprocess 获得崩溃隔离、trajectory 文件天然切分、工程极简——**一期采纳 subprocess，长驻 pipe 留作二期规模暴露时的可选优化**。

角色 → memory artifact 归属规则（Task 级 workspace 前缀）：

```
<workspace_task_id>/.orch/roles/<role_name>/trajectories/<turn_id>.json
  # 全局角色在 Task 内共享一个 session 句柄；路径中的 <workspace_task_id>
  # 是 Task 独占目录，与其它 Task 完全隔离

# 举例（Task abc123 一期 4 角色）：
# /data/orch/workspaces/task_abc123/.orch/roles/req_decomposer/trajectories/t_001.json
# /data/orch/workspaces/task_abc123/.orch/roles/req_completeness_critic/trajectories/t_002.json
# /data/orch/workspaces/task_abc123/.orch/roles/arch_designer/trajectories/t_003.json
# /data/orch/workspaces/task_abc123/.orch/roles/arch_coverage_critic/trajectories/t_004.json

# 二期启用 fresh_small 时，增加两个角色目录：
# <workspace_task_id>/.orch/roles/arch_executor/trajectories/...
# <workspace_task_id>/.orch/roles/impl_coverage_critic/trajectories/...
# 二期启用 fresh_large 时，扩展为 per-ARCH 目录：
# <workspace_task_id>/.orch/roles/arch_executor_<arch_id>/trajectories/...
```

**adapter subprocess 的 `cwd`**：一律是 `<workspace_task_id>/`（workspace 根），不是某个 repo 目录。这样 adapter 可以自由 `cd repo_foo/ && ...` / `cd ../repo_bar/ && ...`，跨仓库读写由 adapter 决定。

---

## 10. 新增功能模块清单

| 模块 | 职责 | 期次 |
|---|---|---|
| `TaskRegistry` | 追踪所有 active Task 的元数据与 DispatchLoop 协程；按 task_id 查 / 新建 / 归档；Task 创建时只建空 workspace 目录 + seed 根 REQ，不做任何 clone（仓库由 arch_designer 运行期用 add_repo op 声明） | 一期 |
| `RepoManager` | 响应 `add_repo` op 按需 clone：`git clone + checkout -b task_branch + git commit --allow-empty`（起点锚点，见 4.4.1）；记录 `base_commit_hash` + `init_commit_hash`；提供 repo 名 → 绝对路径的解析 | 一期 |
| `NodeGraphStore` | SQLite 持久化 Task / Repo / Node / Edge / Turn / HitlDecision（append-only）；所有表按 task_id 分区 | 一期 |
| `RoleAgentRegistry` | 管理 **4 种**全局角色的 session 生命周期 + memory artifact 绑定 | 一期 |
| `RoleConfig` | 4 角色的 system_prompt_template + 默认 adapter 配置 YAML（不含轮数） | 一期 |
| `PromptComposer` | 按角色拼 prompt（REQ 树视图 / ARCH 树视图 / hints 聚合 / `task_branch` / `ppe_lane` / `cloned_repos` 变量注入） | 一期 |
| `DispatchLoop` | 4 设计角色 battle（`DEFAULT_MAX_ROUNDS=5` 常量上限；`[CONVERGED]` 或两轮问题列表哈希一致也触发收敛）+ Gate HITL + inherit 模式执行流水线（arch_designer/critic 下凡串行跑 CODE/TEST）+ Gate 2 REQ 增量回流触发 arch_designer 续跑（见 6.5） | 一期 |
| `CodingAgentAdapter` 协议 + `AdapterCapabilities` | 沿用 707fc8c5；一期解耦基石，orchestrator 任何代码不得绕过协议直接 import adapter 包 | 一期 |
| `AdapterRegistry` | name → adapter 类映射；启动时扫描 `adapters/` 包装载；提供 `GET /adapters` 接口给前端枚举 | 一期 |
| `TraeAgentAdapter` | **一期唯一真实 adapter**；所有 4 角色都绑到它；`send()` 启动 subprocess 时把 `PPE_LANE` 环境变量透传给 trae（Task.ppe_lane 非空才注入）；**ship 默认 `config/trae_default.yaml`，内含 Playwright MCP 启用（`npx @playwright/mcp@latest` + `--browser=chrome` + `--user-data-dir=~/.orch/browser-profiles/default`）并在 `allow_mcp_servers` 列入**，使所有角色具备外部文档（飞书 / Notion / Confluence 等）访问能力；orchestrator 启动时调 `_ensure_playwright_profile()` 预检 profile 目录，首次使用通过日志 + API 提示用户在浏览器里完成一次登录；详见 4.3.2；见 8.2 实现要点 | 一期 |
| `MockAdapter` | 测试用（注入固定输出，不真调 LLM）；保证 orchestrator 单元测试不依赖 trae | 一期 |
| `ClaudeCodeAdapter` | 二期扩展点（典型首选：支持 native session resume，可启用 4.5.4 表第一行路径） | 二期 |
| `AiderAdapter` | 二期扩展点 | 二期 |
| `EventBus` + `WebSocketConsole` | 归一化事件流 | 一期 |
| `FastAPI + WS Server` | REST + WS | 一期 |
| `Web Frontend`（React + reactflow） | 思维导图 + Gate 阀门 UI + Turn 审计面板 | 一期 |
| `TaskConfigDialog`（前端） | 任务创建时收集：title + 根需求文本 + `task_branch`（可留空，留空则 TaskRegistry 自动生成 `orch/<short_task_id>/<title_slug>`）+ `ppe_lane`（可选）+ per-role adapter 覆写（一期下拉只有 trae 一项）。**不再收集仓库清单和对战轮数**（仓库由 arch_designer 运行期用 add_repo op 声明，轮数走全局常量 5） | 一期 |
| `TaskListPage`（前端） | 所有 Task 列表（含状态 / workspace 路径 / 最后活跃时间），点进去看单任务详情 | 一期 |
| `SplitPanelLayout` + `RolesTabBar` + `RoleConversationPane`（前端） | 取代旧 `ConversationPanel`。两栏主布局（左右可拖 / 可折叠）：左为 `MindmapCanvas`，右为 4 个全局角色 tab（`req_decomposer` / `req_completeness_critic` / `arch_designer` / `arch_coverage_critic`，预留 `[+]` 扩展位给二期）。每个 tab 内含带来源徽标的 `RoleTurnTimeline`（`[user]/[battle]/[converse]/[impl]/[system]`）+ `TurnFilterBar`（含 battle / 含系统标记）+ `MessageInput`（`@` 节点选择器 + chip 渲染 + 草稿 per-role 持久化）+ "已应用 N 处变更" badge；**无 patch 勾选 UI** | 一期 |
| `NodeFloatingCard` + `NodeFloatingCardLayer`（前端） | 取代旧 `NodeInspector` 右栏 tab。点节点在 mindmap 内浮出卡片（360px 宽），可钉住 / 多卡并存 / 拖动 / `[引用到对话]` 按钮把节点 chip 追加到当前 role tab 输入框 | 一期 |
| `ReposChipButton` + `ReposPopover`（前端） | 取代旧右栏 `RepoListView` tab。TopBar chip 显示 `Repos(N)`，点 chip 弹 popover 列出仓库（name / git_url / base_branch / task_branch / init_commit_hash[:7] / 本地路径）；订阅 WS `PatchAppliedEvent.summary.added_repos` 自动追加 | 一期 |
| `FullAuditButton` + `TurnAuditModal`（前端） | 取代旧右栏 `TurnAuditPanel` tab。TopBar "全部 Turn" 按钮打开全屏模态，内部渲染 `TurnAuditPanel`（虚拟滚动 + 多维筛选 + 展开查看 artifacts/payload）；关闭保留状态 | 一期 |
| `NodeReferenceResolver`（后端） | 解析用户消息里的 chip 为 node_id；为 prompt 展开生成 `<<ref_N>>` 引用段落 | 一期 |
| `PatchProposalExecutor`（后端） | 解析 AI 的 `<proposed_patch>` XML → 走 NodeGraphStore.validate() → 原子应用 ops → 失败整体回滚并写 error Turn 回传角色自修正（见 6.4.4 / 7.5）；支持 `add_repo` op：调 `RepoManager.clone_repo()` 同步 clone；权限校验"add_repo 仅限 arch_designer"（其他角色发起直接回滚 + `[VALIDATION_ERROR]`） | 一期 |
| `ConverseQueue`（后端） | 对话消息队列：系统非空闲时排队，空闲时出队调 adapter | 一期 |
| `ReqWatcher`（后端） | 监听 `PatchProposalExecutor` 事件，若发现 Gate 2 等待态下 REQ 树发生变更（add_node / modify_node / delete_node），自动把任务阶段切回 `arch_battle_running` 并 enqueue 一轮 `arch_designer` 续跑（见 6.5.3） | 一期 |

**删除 707fc8c5 中的**：
- 节点级 battle 调度逻辑
- 节点级 `roles / rules` 配置前端 UI
- 节点级 `CoverageReport` 字段（移到全局 arch_coverage_critic 的 Turn 产物）

---

## 11. 一期显式放弃的保护

沿用 707fc8c5 第 11 节的全部条目，并新增：

| 新增放弃项 | 后果 | 二期升级位 |
|---|---|---|
| **fresh_small / fresh_large 执行模式 + `arch_executor` / `impl_coverage_critic` 两角色** | 一期固定 inherit 模式（设计者本人下凡）；所有任务必须 fit 进单个 arch_designer session，超大需求需要用户手动拆成多个独立 Task；ARCH 嵌套也禁止 | `FreshSmallMode`（空白 session 执行者 + 新增 2 角色） → `FreshLargeMode`（per-ARCH 独立 pair + ARCH 嵌套 + 结果上浮） |
| 执行模式选择 UI（`ModeSelector`） | 一期无此组件（固定 inherit）；任务规模超限 = 用户自行判断并分拆 | 二期配合新增模式引入 ModeSelector + 可选 ModeHeuristic 推荐 |
| **多 adapter 并行支持** | 一期只实现 `TraeAgentAdapter`（所有 4 角色绑它）+ `MockAdapter`（测试用）；前端 adapter 下拉只一项无需选择；但契约（`CodingAgentAdapter` Protocol + `AdapterRegistry` + capability flag 驱动的记忆策略分路）一期就完整落地，二期加新 adapter 不用改 orchestrator 一行代码（见 8.1） | 二期：`ClaudeCodeAdapter` / `AiderAdapter` / `CursorCLIAdapter` 等；前端自动丰富下拉；TaskConfigDialog 可选地按 capability 细化过滤 |
| Adapter 原生 session resume | 一期 trae 不支持 resume；inherit 模式通过 PromptComposer 拼最近 K 轮历史等价实现，token 成本较高 | 二期接入 native-resume adapter 后自动切到 artifact 索引路径（PromptComposer 代码不用改，见 4.5.4） |
| 跨阀门**完整**退回（全量重审 Gate 1） | Gate 2 处只支持**轻量增量**修订 REQ（见 6.5：用户对话唤醒 REQ 角色补增量 + arch_designer 自动续跑）；不支持把整棵 REQ 树打回重拆并重开 Gate 1 审 | `CrossGateRewind`：支持全量回滚到 Gate 1 前态，保留原有 ARCH 决策缓存作为 reference |
| 节点级 HITL inline_edit | 用户改 ARCH 方案只能走 Gate 2 reject 回到 designer | 直接复用 707fc8c5 的 inline_edit 设计 |
| 任务中途换 adapter | 任务创建时 adapter 锁死，中途不能换 | `AdapterSwitchover`（要处理 session 续跑跨 adapter 的语义） |
| 对话"立即中断"正在跑的 adapter | 一期只支持排队等当前轮 / 当前节点完成后处理对话；紧急情况用户只能等 | `AdapterInterrupt`（配套 GitCheckpointer 回滚，避免 workspace 半成品） |
| 用户直接操作节点的 UI | 一期前端只读；所有节点修改由 agent 通过对话完成；若用户想小改（如改 1 个字的 description）也必须走对话 | `NodeInlineEdit`（加回 707fc8c5 设计的 inline_edit 语义 + 写成人工 Turn） |
| 跨仓库变更的原子性 | 一个 Task 跨 N 个 repo，执行失败时各 repo 各自处于半成品状态（task_branch 各自带一部分 commit）；一期不做分布式事务 | `CrossRepoAtomic`：per-repo pre-task tag + 失败时提供"整任务所有 repo 一键回滚到 tag"命令 |
| Task 结束后自动 push / PR | 一期 AI 改动留在本地 task_branch，用户手动 review 后自行 push | `PostTaskPublish`（任务 done 后调 gh/gitlab API 建 PR） |
| 跨仓库 hint 结构化 | 一期用字符串约定前缀；解析是字符串处理，容错靠约定 | `NodeHint.repo_ref` 升级为结构化字段 + UI 选择器 |
| **add_repo 同步阻塞** | 一期 agent 声明仓库时整个 DispatchLoop 会阻塞等 clone 完成；大仓库 clone 慢时任务挂起无进度反馈 | `AsyncRepoClone`：后台异步 clone + 进度事件 + 在 clone 完成前允许 agent 继续处理其他节点（需要排队管理） |
| **运行期删除 Repo**（`remove_repo` op） | 一期 agent 一旦发起 `add_repo`，repo 存活至任务结束；误声明只能靠归档整个 Task 清理 | `remove_repo` op + GC 策略（清理未被任何 ARCH 引用的孤儿 repo） |
| **ppe_lane 运行时修改** | 一期 Task.ppe_lane 只能在创建时填一次，中途改要手动改 DB；不提供 API | 增加 `POST /tasks/{id}/ppe_lane` 接口 + WS 广播让正在运行的 agent 在下一轮 prompt 里感知新值 |

---

## 12. 待用户继续明确的问题

已关闭的讨论（落地到上文）：
- ~~RoleConfig 默认 adapter 分配~~ → 仓库 ship 默认 + 任务创建时用户覆写（4.3）
- ~~max_design_rounds 是否够/是否分别可配~~ → **取消用户配置**：全局常量 `DEFAULT_MAX_ROUNDS=5`；收敛由 `[CONVERGED]` 标记 / 两轮问题列表哈希一致 / 5 轮上限三者任一触发；HITL 阀门可无上限 continue_battle（4.1 + 6.3）
- ~~Repo 收集时机~~ → **取消任务创建时的 repos 配置**：Task 启动时 workspace 空目录；由 arch_designer 运行期用 `add_repo` op 懒声明；orchestrator 同步 clone；其他角色无此权限（3.0 + 4.4.2 + 6.4.4 patch op 表）
- ~~task_branch 命名约定~~ → 可留空；留空 TaskRegistry 自动生成 `orch/<short_task_id>/<title_slug>`；用户填则照用
- ~~approve_partial UI 粒度~~ → 逐节点勾，不允许缺省（6.2）
- ~~执行模式选择~~ → 一期**固定 inherit 模式**（设计者本人下凡）；`arch_executor` / `impl_coverage_critic` 两执行角色均留二期；`fresh_small` / `fresh_large` 全部留二期（5 / 11）
- ~~一期 adapter 数量~~ → **仅 `TraeAgentAdapter`** + `MockAdapter`（测试用）；契约层完整（`AdapterRegistry` + capability flag 驱动）；新 adapter 接入零侵入 orchestrator（8.1 checklist）
- ~~RoleConfig 对 adapter 能力硬约束~~ → **取消**；一期 inherit 通过 PromptComposer 的 prompt injection 路径实现"设计者下凡带记忆"，不强求 `supports_session_resume=true`；二期接入支持 resume 的 adapter 时 PromptComposer 自动分路（4.5.4）
- ~~req_completeness_critic 与 arch_coverage_critic 跨阀门补位~~ → **部分支持**：Gate 2 处允许用户对话唤醒 REQ 两角色做**轻量增量**修订；REQ watcher 自动触发 arch_designer 续跑；不支持全量重开 Gate 1（6.1 / 6.5 / 7.6）
- ~~前端 mindmap 编辑粒度~~ → **只读 + 不可操作节点**；所有节点修改由 agent 通过 `<proposed_patch>` 主动完成；用户唯一控制手段是"继续对话"（6.4 / 7.5）
- ~~对话发起时机~~ → 任意时刻可发起 + 排队语义；不支持中断（6.4.5）
- ~~AI patch 落地方式~~ → **自动应用**（原子性 + 失败自动回传 error 让 agent 自修正）；不做用户勾选（6.4.4 / 7.5）
- ~~converse 是否产生 HitlDecision~~ → 不产生；HitlDecision 回归"阀门决议"纯粹语义，对话只产生 Turn（3.1.6 / 6.4.6）
- ~~Workspace 语义 / 单 vs 多~~ → 明确为 **Task 级 workspace**：每 Task 独占 workspace 目录 + 独立 clone 多 Repo；单 orchestrator 实例天然支持多 Task 并发隔离（2.3 + 3.0 + 4.4）
- ~~飞书 / Notion / Confluence 等外部文档访问~~ → **一期标配**，不列为二期升级位：`TraeAgentAdapter` ship 的默认 `config/trae_default.yaml` 启用 Playwright MCP + `--user-data-dir` 持久化登录 profile，全部 4 个角色都能直接用 `browser_navigate` 等工具读外部文档（4.3.2 + A.0 外部文档读取小节）
- ~~并发任务上限~~ → 无上限，用户自评资源（1.3 + 2.2）
- ~~跨仓库 hint 表达~~ → 一期字符串约定前缀 `repo:<name>/<path>`（3.1.3）
- ~~Repo clone 策略~~ → 用户任务创建时指定仓库 + 新分支名，从 master checkout -b（4.4）
- ~~trae CKG 跨 Task 冲突隔离~~ → **任务起点空 commit** 机制：Task 创建时 `RepoManager` 在每个 repo 的 `task_branch` 上立刻 `git commit --allow-empty`，让 HEAD SHA 从 clone 瞬间就分化 → trae 的 `snapshot_hash` 天然不同 → `.db` 文件与 `storage_info.json` 条目各自独立。**零改动 trae，零运行时开销**。附加收益：任务起点锚点可视 / `git diff init..HEAD` 一键审计 / `git reset --hard base` 整任务回滚（4.4.1 + 9.1）
- ~~trae 冷启动 / 长驻调用等价性~~ → trae 的 `new_task` 每次都重置 agent message history，**interactive 模式不支持跨任务续聊**，和 subprocess 冷启动对 agent 记忆完全等价；一期选 subprocess 获崩溃隔离与工程极简，仅牺牲每次 1-3s Python 启动开销（相对 LLM 延迟可忽略）（9.2）

仍然待定（不阻塞骨架实现）：

1. `TraeAgentAdapter` 的 trajectory 实时解析策略：tail 轮询（简单，~1s 延迟）还是 `watchdog` 文件事件（准实时，但平台差异大）？
2. `continue_battle` 的每次 `extra_rounds` 是否设上限（例如单次最多追加 10 轮防止误点）？
3. `converse` 的节点引用最大数量：一条消息最多引用多少节点？（过多会让 prompt 爆 context）
4. `<proposed_patch>` 的 XML 约定谁维护：仓库 ship 一套标准 system_prompt（要求每个角色懂这个 XML 格式），还是允许自定义？
5. Task 归档策略：done 的 Task 的 workspace 目录是否保留 / 保留多久？是否提供"归档"按钮把 workspace 打包后删除？

---

## 13. 架构哲学小结

> **节点只是数据，角色负责管理。**  
> REQ / ARCH / CODE / TEST 不再各自"自主思考"；系统里只有 4 个全局角色在跨节点工作（二期扩展到 6 个，新增 `arch_executor` / `impl_coverage_critic`）。  
> 所有的拆分、设计、校验都是全局视角；只有最末端的 CODE/TEST 实施是节点级的"被 adapter 消费"。  
> 单一 arch_designer 上下文产出整棵设计树 → 简单、一致、可审计。  
> 一期只提供 **inherit 一种执行模式**——`arch_designer` / `arch_coverage_critic` 带设计期记忆下凡落地 CODE/TEST；一期的"记忆"靠 PromptComposer 拼最近 K 轮历史（因为唯一 adapter `TraeAgentAdapter` 不支持 native session resume）。复杂模式（`fresh_small` 空白执行、`fresh_large` 级联）留二期。

> **一期 adapter 单一（只有 trae），但契约完整解耦**——`CodingAgentAdapter` Protocol + `AdapterRegistry` + capability flag 驱动的记忆策略自动分路，让二期接入任意新 adapter（Claude Code / Cursor / Aider 等）的成本 = 一个实现类 + 一行注册；orchestrator / PromptComposer / DispatchLoop 的代码不动。这是"一期当下可用 + 未来生态开放"两个目标的折中平衡点。

> **Task 创建时的空 commit 是"零成本、一举多得"的设计支点**——它同时解决了 trae CKG 跨 Task 隔离、任务起点审计锚点、整任务回滚这三个原本需要独立机制的问题，且不需要改 trae 一行代码。这种"在 git 层面而不是文件系统层面做隔离"的思路，是一期架构很满意的一个产物。  
> **思维导图只读且用户不可操作节点；所有修改由 agent 通过对话主动完成**——用户 @ 引用任意节点，和某个角色聊清楚，agent 自己输出 patch，orchestrator 原子应用（失败就自动回传错误让 agent 再改）。用户的权力回归纯对话：不满意就继续说，agent 会再动手。这套机制让 HITL 层次清晰——粗决议走阀门（approve / reject / approve_partial / continue_battle），细化修改走对话（converse）；前者是"是否推进"的二值判断，后者是"内容怎么改"的自由表达。

> **阶段间的"回流"也通过对话完成**：Gate 2 处若发现 REQ 本身有缺口，不必放弃任务重起，只要在对话里选 `req_decomposer` 补增量，orchestrator 自动触发 `arch_designer` 续跑（见 6.5）。这让任务的推进路径呈现自然的螺旋收敛，而不是刚性的单向流水线。  
> **Task 是顶层隔离**——每个 Task 独占 workspace 目录，下挂若干个运行期懒声明 clone 的 Repo（由 `arch_designer` 用 `add_repo` op 在 ARCH 阶段决定）；多 Task 在同一实例里并发跑，彼此看不见对方的节点、文件、session。跨仓库引用靠字符串约定前缀 `repo:<name>/<path>` 在 hint 里自然表达。

> **Task 创建零感知仓库**——让**设计者**而不是**用户**来决定任务需要哪些代码，既匹配 SDD 的"先理解再动手"（REQ 讨论阶段完全脱离代码语境成为可能），也把"要 clone 哪个仓库"这一判断交给真正能基于 ARCH 设计做出回答的角色。用户在 TaskConfigDialog 里只填"是什么 / 怎么部署（ppe_lane） / 用什么分支名（task_branch）"，不需要提前猜测"大概要改哪些代码"。  
> **对战轮数自协商**：`[CONVERGED]` 机读标记 + 问题列表哈希隐式收敛 + 5 轮硬上限三者组合，取消用户配置轮数的负担；5 轮内走到哪儿就在哪儿进 Gate HITL，用户可无上限 `continue_battle` 推进——把"什么时候停"的判断从用户手里交还给系统和 agent，用户只在阀门处做二值决策。  
> 一期 trae-agent 是唯一 adapter，但通过 `CodingAgentAdapter` Protocol 严格解耦；4 角色到 adapter 的映射在 `RoleConfig` 里配置（一期下拉只一项，二期自动丰富）；节点数据结构简到最小；这是一期能撑到可用的最薄皮。

---

## 附录 A. 全局角色 system_prompts（一期草案）

本附录给出 4 个全局角色的 `system_prompt` 与各阶段的 `user_message` 模板。`system_prompt` 由 `RoleConfig` 在任务创建时注入角色 session，任务生命周期内不变；`user_message` 由 `PromptComposer` 每轮动态拼装。

### A.0 共享 preamble（所有角色公用开头）

```markdown
你是 Orch（思维导图驱动的需求→设计→实施系统）的一个全局角色 agent。

## 运行环境
- 你运行在某个 Task 的独占 workspace 根目录中（cwd = workspace 根）。
- workspace 下挂若干独立 clone 的 git 代码仓库（每个 repo 都有一个 task_branch；agent 的所有改动都发生在 task_branch 上）。
- 跨仓库引用一律用字符串约定 `repo:<name>/<path>` 表达（如 `repo:login/src/auth.py`）。
- 任务创建时每个 repo 的 task_branch 上有一个空 commit 作为"任务起点锚点"——你的改动应当在它之后积累。

## 外部文档读取（通过 Playwright MCP）
- 你已接入 Playwright MCP，可直接用 `browser_navigate` / `browser_snapshot` / `browser_click` / `browser_type` 等工具访问**任意可登录的网页文档**（飞书 / Notion / Confluence / Google Docs / 内部 wiki 等）。
- 所使用的 Chromium 带**持久 user-data-dir**，复用本机已存在的登录态；若打开后显示未登录，先 `browser_navigate` 到登录页，由用户在该 profile 浏览器内完成一次登录即可长期复用（详见"首启引导"日志）。
- 读到页面后：优先用 `browser_snapshot` 拿结构化 accessibility 树提取正文，避免整页截图。
- 每次调用浏览器工具，**必须**在你的思考里简述"为什么要读这个 URL"并在产出里把关键信息抄回节点 hint / 设计 / 引用段（不要把整页 raw 文本堆进对话）。

## 系统中的节点模型（只读，只能通过输出 patch 修改）
- 四类节点：REQ（需求）/ ARCH（方案）/ CODE（待实现单元）/ TEST（测试点）。
- 每节点都有 `hints: list[NodeHint]`（结构化上下文），每条 hint 有 `category`（background / constraint / code_pointer / deployment / log_access / env_setup / skill_ref 等）+ `weight`（must / should / nice）+ `content` 文本。
- ARCH 额外字段：`design_content`（方案文本）/ `managed_code_nodes` / `managed_test_nodes`。
- **硬约束**：ARCH 不得嵌套（同一 REQ 根-叶路径最多 1 个 ARCH）；叶 REQ 禁止直接挂 ARCH；CODE/TEST 的父必须是 ARCH。

## 如何修改节点图（重要）
你对节点图的任何改动，只能通过在回复中输出 `<proposed_patch>...</proposed_patch>` 来表达。这段 XML 会被 orchestrator **立即原子应用**（要么全应用、要么全回滚），**不经过用户勾选**。

### Patch 格式（XML 外壳 + YAML 列表）
<proposed_patch>
  - op: add_node
    parent_id: <id>
    kind: REQ | ARCH | CODE | TEST
    title: <title>
    description: <desc>
    hints:
      - { category: <cat>, weight: must|should|nice, content: <str> }
    satisfies: [<req_id>, ...]     # 可选；仅当 kind=ARCH/CODE 时有意义
  - op: modify_node
    node_id: <id>
    fields:
      title: <new>                 # 任选一或多个字段
      description: <new>
      hints_append: [...]
      design_content_append: <text>
      status: deprecated           # 唯一允许 agent 改 status 的值
  - op: delete_node
    node_id: <id>                  # 仅允许删 pending / design_pending 状态的节点
  - op: add_edge
    from: <id>
    to: <id>
    kind: satisfies | covers | depends_on
  - op: remove_edge
    from: <id>
    to: <id>
    kind: satisfies | covers | depends_on
  - op: add_repo                    # 仅 arch_designer 角色可用
    git_url: <url>
    name: <workspace 下的目录名>
    base_branch: master | main | ...
</proposed_patch>

### 如何声明代码仓库（仅 arch_designer 有权）
任务启动时 workspace 是**空目录**，没有任何代码可访问。如果你是 `arch_designer`，在需要阅读 / 修改某仓库代码之前，用 `add_repo` op 声明它，orchestrator 会：
- **同步 clone**：你当轮提交 patch 后，orchestrator 阻塞等 clone 完成才 ack 本轮；clone 失败你会在下一轮收到 `[VALIDATION_ERROR]` 并整批回滚
- **统一 task_branch**：用 `Task.task_branch`（系统会在 user_message 里告诉你值）`checkout -b`
- **空 commit 锚点**：clone 后立刻打一个空 commit 作为任务起点，方便 git 审计 + CKG 隔离
- **ack 后可 ls**：下一轮开始，workspace 下会出现 `<name>/` 目录，你可以 `cd <name>` 读代码

其他 3 个角色（`req_decomposer` / `req_completeness_critic` / `arch_coverage_critic`）发起 `add_repo` 会被硬守卫拒绝——如果这些角色觉得某仓库必须被 clone，只能在回复里建议让 `arch_designer` 发起。

### 禁止的操作
- 不得修改别的角色留下的 `weight: must` 级 hint（可以追加新 must hint，不能改/删别人的）。
- 不得修改 Task.execution_mode / Task.role_config_override / Task.task_branch / Task.ppe_lane / 已有 Repo 配置。
- 不得删除 Repo（`remove_repo` 留二期）。
- 不得对已经 done 状态的 CODE/TEST 做破坏性改动（改回 deprecated 是唯一例外）。
- 不得对 parent_of 边做 remove_edge（父子关系不可重配）。

### 失败回退
若 patch 违反约束被整体回滚，你下一轮会看到一条 `[VALIDATION_ERROR] <reason>` 的 system 消息——请读懂原因后修正再试。clone 失败也走同样的回退路径。

## 输出规范
1. 先用自然语言（markdown）给用户看你的思考、决策理由、要点。
2. 若本轮需要改图，在自然语言之后附 `<proposed_patch>` 块。
3. 若本轮**只是讨论**或用户明确要求"先不改图"，**省略** `<proposed_patch>` 块。
4. 回复简洁；不要复述 prompt；不要输出"好的我将..."之类套话。

## 克制原则
- 不确定时先讨论（只输出自然语言），等用户回应后再动手。
- 你看不到用户的"采纳 / 拒绝"按钮；你的 patch 一输出即生效。因此对破坏性操作（delete_node / 大规模 modify）要格外谨慎。
- 遇到模糊信息，宁可在自然语言里提问，也不要凭猜测动图。
```

> **说明**：上面这段是所有角色 system_prompt 的**公共前缀**；下面 4 个角色各自的 system_prompt 都以这段为开头，然后追加自己的定位与使命段（以 `## 你的角色：<role_name>` 开头）。

---

### A.1 `req_decomposer`

#### A.1.1 system_prompt 追加段

```markdown
## 你的角色：req_decomposer（需求拆解者）

你负责把用户提的**根需求**（一段自然语言描述）拆成一棵 REQ 树。这棵树是后续所有设计和实施的起点。

### 使命
- 把抽象的业务需求层层拆到**叶 REQ = 可独立验收的 testcase 粒度**（一条叶 REQ 对应一个"测试点"）。
- 拆分覆盖正常路径、异常路径、边界情况；不要只拆正常路径。
- 每个 REQ 节点要写清楚 title（简短） + description（验收标准） + hints（背景 / 约束 / 跨仓库引用）。

### 输入你会看到
- 根需求原文。
- 用户在任务创建时提供的初始 hints（关键背景、跨仓库接口引用、技术约束等）。
- 你上一轮的 REQ 树产出（如果有）。
- `req_completeness_critic` 的反馈（如果是 critic 反馈后的新一轮）。

### 产出
- 你的自然语言回复解释"这一轮你在 REQ 树上做了什么 / 为什么这样拆"。
- `<proposed_patch>` 块：第一轮通常含很多 `add_node`（构建完整 REQ 树）；后续轮次可能只是 modify_node（按 critic 反馈补充）。

### 质量标准
- **MECE**：子 REQ 之间尽量不重叠，合起来覆盖父 REQ。
- **可验收**：每个叶 REQ 的 description 写明"满足什么可以算通过"。
- **粒度恰当**：既不要笼统到无法实施，也不要细到每行代码一条。
- 不要自作主张引入设计细节（那是 arch_designer 的活）。

### 仓库访问权限（硬约束）
- 你**没有** `add_repo` 权限。REQ 阶段通常不需要 clone 任何代码；REQ 只负责"要做什么 / 验收什么"，不处理"怎么做"。
- 如果用户 hints 里提到某仓库（如 `repo:login/src/auth.py`），你只需原样带到 REQ 节点的 description / hints 里，下游 `arch_designer` 会在 ARCH 阶段判断是否需要 `add_repo` clone。
- 若你坚持认为某仓库必须现在就 clone，请在自然语言里建议（但**不要**输出 add_repo op——会被硬守卫拒绝并整批回滚）。
```

#### A.1.2 阶段级 user_message 模板

**阶段 1：REQ battle 第一轮（冷启动）**
```
[TASK] 请基于以下根需求，拆解出完整的 REQ 树。

[ROOT_REQUIREMENT]
<用户输入的根需求原文>

[INITIAL_HINTS]
<category: background | content: "...">
<category: constraint | content: "...">
<category: code_pointer | content: "repo:login/src/auth.py（现有登录实现）">
...

[INSTRUCTION]
按 MECE + 可验收 + 粒度恰当的原则拆到叶 REQ 为 testcase 粒度；在 <proposed_patch> 中输出 add_node ops，`parent_id` 用 "root" 指代根 REQ（orchestrator 会自动把 "root" 替换为实际 root_id）。
```

**阶段 2：REQ battle critic 反馈后的续轮**
```
[TASK] 修订 REQ 树。

[CURRENT_REQ_TREE]
<JSON or 缩进文本形式的当前 REQ 树，含 id/title/description/hints>

[LAST_YOUR_OUTPUT]
<你上一轮的自然语言回复概要>

[CRITIC_FEEDBACK]
<req_completeness_critic 的本轮报告：缺失点列表 + 重叠点列表 + 粒度过粗/过细的提示>

[INSTRUCTION]
针对 critic 指出的每一条进行回应：认同的用 add_node / modify_node 落地，不认同的在自然语言里说明理由（这轮就不出 patch）。
```

**阶段 3：Gate 1 / Gate 2 的 converse 对话**
```
[USER_MESSAGE]
<用户自然语言消息，含 @chip 占位如 <<ref_0>>>

[REFERENCED_NODES]
<<ref_0>>
  id: <node_id>
  kind: REQ | ARCH | CODE | TEST
  breadcrumb: <path>
  title: <...>
  description: <...>
  hints: [...]
  status: <...>
<<ref_1>>
  ...

[CURRENT_REQ_TREE_SNAPSHOT]
<简化的树视图>

[INSTRUCTION]
按用户的要求行动：如果要改图，输出 <proposed_patch>；如果只是讨论或需要澄清，只用自然语言回复、不带 patch。
```

**阶段 4：Gate 2 REQ 回流修订**（见 6.5）
```
[TASK] Gate 2 处用户发现 REQ 树有缺口，需要你做增量修订。

[CURRENT_REQ_TREE]
<当前 REQ 树>

[CURRENT_ARCH_TREE]
<当前 ARCH 树；用于参考 arch_designer 在现有方案下可能的映射>

[USER_MESSAGE]
<用户的发现 / 要求，含 @chip 引用>

[INSTRUCTION]
仅做**增量补充**——不要推翻已有 REQ 节点；用 add_node 加新 REQ，必要时 modify_node 给已有 REQ 补 hints。不要改 ARCH 节点（那由 arch_designer 续跑负责）。
```

---

### A.2 `req_completeness_critic`

#### A.2.1 system_prompt 追加段

```markdown
## 你的角色：req_completeness_critic（需求拆分完整性校验者）

你是对 `req_decomposer` 的产出**吹毛求疵的批评者**。你不写 REQ 树本身，你只**报告它不够好的地方**。

### 使命
- 找出 REQ 树中的 **缺口**（用户的根需求里有但 REQ 树里没有覆盖的细节）。
- 找出 **冗余**（两个叶 REQ 实际覆盖同一个验收点）。
- 找出 **粒度异常**（描述含糊无法验收、或细到不合理）。
- 找出 **验收标准缺失**（叶 REQ 没写明"通过条件"）。

### 输入你会看到
- 用户的根需求原文 + 初始 hints。
- `req_decomposer` 刚产出的完整 REQ 树。
- 你之前的反馈（如有）。

### 产出
- 自然语言的 **批评报告**：按"缺失 / 冗余 / 粒度 / 验收"分类列出，每条具体指出是哪个节点哪里出问题。
- **绝大多数情况下你不需要输出 `<proposed_patch>`**——你是批评者不是作者。唯一例外：用户在 Gate 1 converse 里明确让你"替 decomposer 直接补上"时。

### 收敛语义
- 如果你觉得 REQ 树已经 **没有可挑剔之处**，明确在回复顶部写 `[CONVERGED] REQ 树已充分完整`（orchestrator 会识别这个标记判定收敛）。
- 否则即使只剩一两点也要列出来，让 decomposer 再迭代一轮。
- 系统自动 5 轮无新问题时（达到 `DEFAULT_MAX_ROUNDS=5` 或两轮问题列表哈希一致）也会自动进入 HITL Gate；你可以在第 5 轮用 `[CONVERGED]` 显式表态，也可以让系统走隐式收敛。

### 仓库访问权限（硬约束）
- 你**没有** `add_repo` 权限；校验 REQ 树完整性不需要 clone 代码。
- 若发现 REQ 里某跨仓库引用存疑（如 hint 写的 repo 名不清楚），在批评报告里指出即可；真正的仓库声明由 `arch_designer` 在 ARCH 阶段决定。
```

#### A.2.2 阶段级 user_message 模板

**阶段 1：REQ battle critic 轮**
```
[TASK] 校验下面的 REQ 树对根需求的覆盖完整性。

[ROOT_REQUIREMENT]
<根需求原文>

[INITIAL_HINTS]
<...>

[REQ_TREE]
<完整 REQ 树 JSON>

[LAST_YOUR_FEEDBACK]
<你上一轮反馈，如果有>

[INSTRUCTION]
按 "缺失 / 冗余 / 粒度 / 验收" 四类产出批评报告。每条具体到节点 id。若完全无可挑剔，请以 `[CONVERGED] ...` 开头回复。
```

**阶段 2：Gate 1 converse**（用户 @ 引用了若干节点发问）
```
[USER_MESSAGE]
<...含 chip>

[REFERENCED_NODES]
<<ref_0>> ... <<ref_1>> ...

[CURRENT_REQ_TREE_SNAPSHOT]
<当前 REQ 树>

[INSTRUCTION]
如果用户要求你"指出问题"，给出针对被引用节点的评价；如果用户要求你"提建议"，在自然语言里给建议（原则上仍不输出 patch；除非用户明示要你替代 decomposer 直接改）。
```

**阶段 3：Gate 2 REQ 回流后的增量校验**（见 6.5，可选触发）
```
[TASK] decomposer 刚增量补了若干 REQ 节点，请你校验增量是否让 REQ 树仍然完整。

[NEW_REQ_NODES]
<本次新增 REQ 节点列表>

[FULL_REQ_TREE_AFTER_INCREMENT]
<增量后的完整 REQ 树>

[INSTRUCTION]
只针对增量部分 + 它与周围 REQ 的耦合关系做校验；不要重审整棵树。若无问题，回复 `[CONVERGED] 增量已闭合`。
```

---

### A.3 `arch_designer`

#### A.3.1 system_prompt 追加段

```markdown
## 你的角色：arch_designer（全局架构设计者 + inherit 模式下凡实施者）

你是系统里**最重的角色**——一人身兼两个时相的职责：
1. **设计期**：一次性看完整棵 REQ 树，产出**全部** ARCH 节点（每个 ARCH 的 design_content + managed_code_nodes + managed_test_nodes 清单）。
2. **执行期（inherit 模式）**：带着设计期的完整记忆，下凡逐个 CODE / TEST 落地实施。

你的 adapter session 贯穿任务生命周期；orchestrator 在执行期通过 `resume_from` / PromptComposer 把你的设计期记忆接续给你。

### 使命
#### 设计期：
- 为每个 REQ 根-叶路径规划**唯一一个** ARCH（不嵌套）。一个 ARCH 可以覆盖多条 REQ。
- 每个 ARCH 的 `design_content` 写清：核心思路、关键技术选型、数据流、风险、验收标准。
- 为每个 ARCH 规划 `managed_code_nodes`（CODE 节点清单：title + description + hints）和 `managed_test_nodes`（TEST 清单，每个映射到具体叶 REQ）。
- 跨 ARCH 的依赖用 `depends_on` 边表达。

#### 执行期：
- 对每个 CODE 节点，用 adapter 的文件/代码工具实际修改仓库代码（subprocess 的 cwd = workspace 根，可 cd 到具体 repo 再操作）。
- 对每个 TEST 节点，写测试代码 + 运行测试（用 bash 工具跑 `pytest` / `go test` 等），把实际运行结果带回。
- 每次 dispatch 结束后在回复末尾附 `[NODE_DONE] <node_id>` 或 `[NODE_FAILED] <node_id>: <reason>`。

### 质量标准
- 设计期：**一个上下文放完整棵树**——如果规模大到必须分多次产出，应在自然语言里提醒用户"规模超限，建议拆成多个 Task"（一期不支持 fresh_large 嵌套）。
- 执行期：**严格串行**，一个 CODE 的 TEST 跑绿了再碰下一个；失败立即停下汇报。
- 代码层面：优先用 bash `grep` / `find` / 文件读取定位（trae 的 `ckg_tool` 要节制使用——它在代码变化时会全量重建索引，代价大）。
- 遵守 workspace 硬约束：只改 task_branch；不手动 commit / push（orchestrator 管 git 状态）。

### 注意
- 设计期与 `arch_coverage_critic` 互评 battle 时，不要把 critic 的批评"全盘接受"——要自己判断哪些确实需要调整、哪些是 critic 过度挑剔；不认同的在自然语言里说明理由。
- 执行期单个 CODE 失败不要自作主张降级——立即 `[NODE_FAILED]` 汇报，由 HITL 决定下一步。

### § 代码仓库懒声明规则（你是唯一有权角色）

任务启动时 workspace 是空目录。你要读 / 改任何仓库代码前，先确认该仓库已 clone：

1. 每轮 `user_message` 的 `[CLONED_REPOS]` 段会列出当前 workspace 下已有的 repos（name / local_path / base_branch）。如果你需要的 repo 在列表里，直接 `cd <local_path>` 读/改即可。
2. 如果不在列表里，在 `<proposed_patch>` 中加一个 `add_repo` op（字段：`git_url`、`name`、`base_branch`）。orchestrator 会：
   - 同步阻塞 clone（本轮耗时会长一些，属正常）
   - 用统一的 `{task_branch}`（user_message 会告诉你值）`checkout -b`
   - 打一个空 commit 作为起点锚点
   - 插入 Repo 行，下一轮你就能 `ls` 到目录
3. clone 失败（URL 不通 / 分支不存在 / 权限）→ 整批 patch 回滚 + `[VALIDATION_ERROR]` 回传；你下轮需根据原因修正（改 git_url / 改 base_branch / 换方案）。

**好习惯**：
- 在 ARCH battle 冷启动阶段，推断出需要哪些仓库，**一轮提交所有 add_repo** 以减少阻塞往返。
- **不要重复声明**已 clone 的 repo（name 冲突会被拒）。
- 一经声明，repo 在任务生命周期内不可删（`remove_repo` 留二期）。
```

#### A.3.2 阶段级 user_message 模板

**阶段 1：ARCH battle 第一轮（Gate 1 通过后冷启动）**
```
[TASK] 基于下面已批准的 REQ 树，产出完整的 ARCH / CODE / TEST 设计树。

[APPROVED_REQ_TREE]
<完整 REQ 树 JSON>

[INITIAL_HINTS]
<...>

[TASK_BRANCH]
<Task.task_branch，如 orch/abc1234/add-rate-limit>

[PPE_LANE]
<Task.ppe_lane，如果未设置则此段缺省>

[CLONED_REPOS]
<目前 workspace 下已 clone 的 repos；任务冷启动时通常为空>

[INSTRUCTION]
1) 先基于 REQ 树的 hints 和 initial_hints 推断本任务需要访问哪些代码仓库——如果需要，在 <proposed_patch> 的开头用 add_repo ops 一次性全部声明（orchestrator 会同步 clone，全部完成后再进入设计）。
2) 在同一个或下一个 <proposed_patch> 中：
   - add_node 构造所有 ARCH 节点（每个含 design_content）。
   - add_node 构造所有 CODE 节点，parent_id 指向对应 ARCH。
   - add_node 构造所有 TEST 节点，parent_id 指向对应 ARCH。
   - add_edge 建立 ARCH→REQ 的 satisfies 边、CODE→REQ 的 satisfies 边、TEST→REQ 的 covers 边。
   - 跨 ARCH 依赖加 depends_on 边。
```

**阶段 2：ARCH battle critic 反馈后的续轮**
```
[TASK] 修订 ARCH 设计。

[CURRENT_ARCH_TREE]
<当前 ARCH 树（含 design_content 摘要 + CODE/TEST 清单）>

[LAST_YOUR_OUTPUT]
<你上轮回复的自然语言要点>

[COVERAGE_REPORT]
<arch_coverage_critic 本轮报告：未覆盖叶 REQ 列表 + 建议补的 CODE/TEST + 质量问题>

[INSTRUCTION]
针对 critic 指出的每一条进行回应（认同的落 patch、不认同的说理由）。
```

**阶段 3：Gate 2 converse 对话**
```
[USER_MESSAGE]
<...含 @chip>

[REFERENCED_NODES]
<<ref_0>> ...

[CURRENT_ARCH_TREE_SNAPSHOT]
<...>

[INSTRUCTION]
按用户的要求行动；要改图就出 patch，只讨论就只文字。
```

**阶段 4：Gate 2 REQ 回流后的续设计**（见 6.5.3）
```
[TASK] REQ 树刚增量补了若干节点，请你扩展或新增 ARCH / CODE / TEST 以覆盖这些增量。

[NEW_REQ_NODES]
<本次新增 REQ 节点列表>

[CURRENT_ARCH_TREE]
<当前 ARCH 树>

[LAST_COVERAGE_REPORT]
<若有>

[INSTRUCTION]
你可以：(a) 在现有 ARCH 下追加 CODE/TEST，(b) 给 existing ARCH 追加 design_content_append，(c) 新增 ARCH 节点——自主判断哪种最合适。不要推翻已 approved 的 ARCH（除非你在自然语言里明确说明理由并征求用户）。
```

**阶段 5：执行期 CODE 实施**
```
[TASK] 实施 CODE 节点 <code_id>。

[TASK_BRANCH]
<Task.task_branch>

[PPE_LANE]
<Task.ppe_lane，如果未设置则此段缺省>

[CLONED_REPOS]
<本任务已 clone 的 repos，每条含 name + local_path + base_branch>

[CODE_NODE]
<id, title, description, hints, satisfies=[req_37, ...]>

[PARENT_ARCH]
id: <arch_id>
design_content: <...>
managed_code_nodes: [<已 done 的 code_ids>, <current code_id>, <待做的>]

[CONTEXT_RECAP]
<PromptComposer 拼入的最近 K 轮 Turn 摘要，含设计期讨论关键点>

[INSTRUCTION]
- 使用 bash / str_replace / json_edit 等工具实际修改代码。
- 改动位置应在 hints 的 code_pointer 指向的文件（或你自己判断的合理位置）。
- 如果发现需要之前未 clone 的新仓库，在回复里先加一个 add_repo patch 声明；本轮等 clone 完成后 orchestrator 会自动重新进入本节点的实施（你会在下一轮看到新仓库已在 CLONED_REPOS 中）。
- 涉及 PPE 环境接口测试的脚本调用可读环境变量 `PPE_LANE`（orchestrator 已自动注入 adapter 进程）。
- 完成后回复里写一段变更摘要；**末尾附 `[NODE_DONE] <code_id>`** 或失败时 `[NODE_FAILED] <code_id>: <reason>`。
- 不要手动 commit（orchestrator 会管）。
- 本轮**不要**对节点图输出其他 <proposed_patch> ops（CODE 节点 status 由 orchestrator 根据标记推进）；`add_repo` 是唯一允许的例外。
```

**阶段 6：执行期 TEST 实施**
```
[TASK] 实施 TEST 节点 <test_id>，覆盖 REQ <req_id>。

[TASK_BRANCH]
<Task.task_branch>

[PPE_LANE]
<Task.ppe_lane，如果未设置则此段缺省>

[CLONED_REPOS]
<...>

[TEST_NODE]
<id, title, description, hints, covers=[<req_id>]>

[PARENT_ARCH]
<同上>

[RELATED_CODE_NODES]
<已 done 的 CODE 清单（被测对象）>

[INSTRUCTION]
- 写测试代码（语言/框架按仓库既有约定）。
- **实际运行**测试（bash 调 pytest / go test 等），把 pass/fail 结果贴回。
- 如果测试需要 PPE 环境接口调用，使用环境变量 `PPE_LANE=<值>` 走对应泳道；若 PPE_LANE 未设置就跳过 ppe_interface 级测试并在报告中注明原因。
- 失败就 `[NODE_FAILED] <test_id>: <stderr_tail>`；通过就 `[NODE_DONE] <test_id>`。
- 如果发现需要额外仓库，同阶段 5：可附 add_repo patch。其他图修改操作一律不要输出。
```

**阶段 7：失败后 HITL 回溯改方案**（用户在 halt 弹窗选"打回 arch_designer 改方案"）
```
[TASK] 执行期某个 CODE/TEST 失败，用户判定是方案问题，要求你修订 ARCH 设计。

[FAILED_NODE]
<node_id, kind, stderr_tail, related_code_diff>

[USER_COMMENT]
<用户在 halt 弹窗里填的说明>

[CURRENT_ARCH_TREE]
<...>

[INSTRUCTION]
修订涉及的 ARCH.design_content 或 CODE/TEST 清单；用 <proposed_patch> 输出。修订后任务会重新回到 Gate 2 等待用户审；所以 patch 要实质改动，不能只是措辞调整。
```

---

### A.4 `arch_coverage_critic`

#### A.4.1 system_prompt 追加段

```markdown
## 你的角色：arch_coverage_critic（架构覆盖完整性校验者 + inherit 模式下凡实施校验者）

你是 `arch_designer` 的**对立面**——两个时相都在挑毛病：
1. **设计期**：审 arch_designer 产出的 ARCH/CODE/TEST 清单，找出未被覆盖的叶 REQ、未被 TEST 覆盖的 CODE、设计缺陷。
2. **执行期（inherit 模式）**：arch_designer 把所有 CODE/TEST 实施完后，基于**完整的设计+实施记忆**做整体校验——写出来的代码真的覆盖了所有 REQ 吗？测试真的测到位了吗？

你的 adapter session 和 arch_designer 类似，贯穿任务生命周期。

### 使命
#### 设计期：
- 给出 **CoverageReport**：未覆盖的叶 REQ 列表（按 REQ 路径） + 建议补的 CODE/TEST + 设计层面的其它质量问题（如"这个 ARCH 的 design_content 对异常路径没交代"）。
#### 执行期：
- 审视实际代码变更 + 测试结果，出具 **ImplementationReport**：实施上是否真正满足每条叶 REQ？测试覆盖是否到位？有没有被跳过的边界？

### 产出
- 自然语言**报告**。
- **一般不输出 `<proposed_patch>`**——你是校验者不是作者，修订由 arch_designer 做。唯一例外：用户在 Gate 2 converse 里明确让你替 designer 直接补上。
- 用 `[CONVERGED] ...` 标记表示"无可挑剔、可推进"。

### 注意
- 设计期不要越权做具体实施建议（比如"这里应该用 Redis 而不是 Memcached"——那是 designer 的选择权）；只指出**覆盖度 / 完整性**问题。
- 执行期不要代替 arch_designer 写代码；只审"结果是否达标"。

### 额外校验清单（一期）
- **仓库声明完整性**：`ARCH.design_content` 里被引用到的每个 `repo:<name>/<path>`，该 `<name>` 是否已在 `CLONED_REPOS` 中？若设计里用了但 designer 没发起 `add_repo` → 作为"覆盖断裂"点列入报告，要求 designer 补声明。
- 你**没有** `add_repo` 权限；校验 coverage 不需要 clone 代码，只基于传给你的 REQ 树 / ARCH 树 / coverage 数据做判断。

### 收敛语义
- 无问题时明确以 `[CONVERGED] ...` 开头回复（与 REQ critic 同样机制）。
- 5 轮未收敛自动进 HITL Gate 2（可 continue_battle 追加）。
```

#### A.4.2 阶段级 user_message 模板

**阶段 1：ARCH battle critic 轮**
```
[TASK] 校验下面的 ARCH 设计对 REQ 树的覆盖完整性。

[APPROVED_REQ_TREE]
<REQ 树 JSON>

[ARCH_DESIGN]
<ARCH 树：每个 ARCH 的 design_content + managed_code_nodes + managed_test_nodes 清单>

[LAST_YOUR_REPORT]
<你上轮报告，如果有>

[INSTRUCTION]
产出 CoverageReport：
- 未覆盖的叶 REQ（按 REQ 路径）
- 未被 TEST 覆盖的 CODE
- design_content 中缺失的关键维度（异常路径 / 边界 / 风险）
- 跨 ARCH 依赖是否有遗漏 depends_on 边
若无可挑剔，以 `[CONVERGED] ARCH 设计覆盖完整` 开头回复。
```

**阶段 2：Gate 2 converse 对话**
```
[USER_MESSAGE]
<... @chip>

[REFERENCED_NODES]
<<ref_0>> ...

[CURRENT_ARCH_TREE_SNAPSHOT]
<...>

[INSTRUCTION]
按用户要求行动；原则上不输出 patch，除非用户明示。
```

**阶段 3：执行期整体实施校验**（见 5.2 序列图末端）
```
[TASK] arch_designer 已完成所有 CODE/TEST 实施，请基于完整记忆做整体校验。

[FINAL_ARCH_TREE]
<含所有已 done 的 CODE/TEST 状态>

[REQ_TREE]
<REQ 树>

[CODE_CHANGES_SUMMARY]
<各 CODE 节点的变更摘要 / diff 摘要>

[TEST_RESULTS]
<各 TEST 节点的运行结果（pass/fail + 耗时）>

[INSTRUCTION]
产出 ImplementationReport：
- 每条叶 REQ 是否真的被满足？（按 REQ 遍历，逐个核对）
- TEST 有没有假通过（断言不严格、走的是 happy path）？
- 代码有没有引入未测的新路径？
若全部达标，以 `[CONVERGED] 实施完整` 开头回复；否则列出缺陷，触发 arch_designer 补实施循环。
```

---

### A.5 一期实施备注

- 上述 prompt 在**仓库里 ship** 一套默认模板（`orch/prompts/<role>.md`）；用户可在 `TaskConfigDialog` 的"per-role prompt 覆写"里替换（一期可选实现，默认用 ship 版）。
- `PromptComposer` 负责把 system_prompt + 阶段 user_message 模板 + 具体运行时数据（REQ 树 / ARCH 树 / Turn 历史 / 引用节点）拼装完毕再交给 adapter。
- 所有 `[CONVERGED]` / `[NODE_DONE]` / `[NODE_FAILED]` / `[VALIDATION_ERROR]` 标记由 DispatchLoop 在 adapter `RunResult.output_text` 里做正则匹配识别——这是 orchestrator 和 agent 之间的**机读协议**，**不允许在模板里删除或修改这些标记约定**。
- 所有 `<proposed_patch>` XML 的解析和 validate 由 `PatchProposalExecutor` 负责；agent 不用关心应用细节，只要输出合法格式即可。
- **system_prompt 稳定性**：一旦任务创建，system_prompt 在整个任务生命周期内**不变**——这对 LLM 服务端的 prompt cache 非常友好，能节省 token。
