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
