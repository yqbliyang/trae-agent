import { create } from "zustand";

export type RoleTab =
  | "req_decomposer"
  | "req_completeness_critic"
  | "arch_designer"
  | "arch_coverage_critic";

interface TaskBrief {
  id: string;
  title: string;
  stage?: string;
}

interface TaskDetailState {
  taskId: string | null;
  task: Record<string, unknown> | null;
  nodes: unknown[];
  edges: unknown[];
  repos: unknown[];
}

interface OrchUiState {
  splitRatio: number;
  activeRoleTab: RoleTab;
  taskList: TaskBrief[];
  detail: TaskDetailState;
  setSplitRatio: (r: number) => void;
  setActiveRoleTab: (t: RoleTab) => void;
  setTaskList: (t: TaskBrief[]) => void;
  hydrateDetail: (payload: Record<string, unknown>) => void;
  resetDetail: () => void;
}

const RATIO_KEY = "orch.splitRatio";

export const useOrchStore = create<OrchUiState>((set) => ({
  splitRatio: Number(localStorage.getItem(RATIO_KEY)) || 0.55,
  activeRoleTab: "arch_designer",
  taskList: [],
  detail: { taskId: null, task: null, nodes: [], edges: [], repos: [] },
  setSplitRatio: (r) => {
    localStorage.setItem(RATIO_KEY, String(r));
    set({ splitRatio: r });
  },
  setActiveRoleTab: (t) => set({ activeRoleTab: t }),
  setTaskList: (list) => set({ taskList: list }),
  hydrateDetail: (payload) => {
    const task = (payload.task as Record<string, unknown>) ?? null;
    const id = (task?.id as string) ?? null;
    set({
      detail: {
        taskId: id,
        task,
        nodes: (payload.nodes as unknown[]) ?? [],
        edges: (payload.edges as unknown[]) ?? [],
        repos: (payload.repos as unknown[]) ?? [],
      },
    });
  },
  resetDetail: () =>
    set({
      detail: {
        taskId: null,
        task: null,
        nodes: [],
        edges: [],
        repos: [],
      },
    }),
}));
