# Orch — Thin Orchestrator (Phase 1)

基于 trae-agent 的思维导图需求拆解与 SDD/TDD 执行系统（一期全局角色极简版）。

## 结构

```
orch/
├── backend/   # FastAPI + DispatchLoop + Adapters (Python 3.12)
└── frontend/  # React + reactflow + Zustand (TS)
```

## 快速开始

### 后端

```bash
cd orch/backend
uv venv --python 3.12 .venv
source .venv/bin/activate
pip install -e ".[test]"
pytest               # 单元测试
uvicorn orch_backend.api.main:app --reload --port 8787
```

### 前端

```bash
cd orch/frontend
npm install
npm test             # Vitest
npm run dev          # 默认 5173 端口
```

## 设计文档

- 主 plan: `.cursor/plans/基于trae-agent的思维导图需求拆解与sdd_tdd执行系统-一期全局角色极简版_a7e3b91c.plan.md`
- 实施 plan: `.cursor/plans/实施_plan_函数组件清单_f4bc0d9b.plan.md`
- 测试 plan: `.cursor/plans/测试清单伴生_plan_db75900d.plan.md`
- 前端 plan: `.cursor/plans/前端界面组件与测试规划_c3d0d72e.plan.md`

同名副本已放在本目录 [`orch/`](.) 根下（与本 README 同级），便于随仓库检出；Cursor 工程中仍以 `.cursor/plans/` 为编辑来源时可忽略副本。

以上为 **4 份** plan 路径（非 5）。若本机 `.cursor/plans/` 无对应正文，可使用本 README 同级目录下的同名 `.plan.md`。

### Plan 与设计复杂度

下面的「设计复杂」主要指系统/领域/前端交互层面的架构设计强度（不单指实现工作量）。

| Plan | 设计复杂度（相对） | 说明 |
|------|-------------------|------|
| 主 plan | 高 | 思维导图拆解语义、编排与任务状态、与 trae-agent 的边界（DispatchLoop / Adapters）、后端 API 与持久化约定 |
| 前端 plan | 中高 | React Flow、画布数据模型、与任务状态的同步（如 WebSocket）、Zustand 与视图一致性 |
| 实施 plan | 低到中等 | 函数/组件清单与工程拆分；一般不单独升格为系统级架构文档 |
| 测试 plan | 低到中等 | 覆盖层级、fixture 与 mock 边界；以质量保证为主，弱化于领域/编排设计 |

实施 plan、测试 plan 单独通常不算「设计很复杂」，但与主 plan 的工作量及耦合仍可能较大。

若以正文细化：出现新业务状态机、并发一致性、多后端集成等章节时，可相应上调对应 plan 的复杂度评级。
