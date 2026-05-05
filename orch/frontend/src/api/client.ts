/** API wrapper — aligns with orch_backend routes (phase 1). */

const BASE = import.meta.env.VITE_ORCH_API ?? "http://127.0.0.1:8787";

async function j<T>(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<T> {
  const r = await fetch(input, init);
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.status === 204 ? (undefined as T) : r.json();
}

export interface CreateTaskPayload {
  title: string;
  root_requirement: string;
  task_branch?: string | null;
  ppe_lane?: string | null;
}

export const apiClient = {
  async listTasks(): Promise<unknown[]> {
    return j<unknown[]>(`${BASE}/tasks`);
  },

  async createTask(
    payload: CreateTaskPayload,
  ): Promise<Record<string, unknown>> {
    return j(`${BASE}/tasks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },

  async getTask(id: string): Promise<unknown> {
    return j(`${BASE}/tasks/${id}`);
  },

  /** GET /tasks/{id}/turns — optional filters match backend query params */
  async listTurns(
    taskId: string,
    filters?: { role?: string; phase?: string },
  ): Promise<unknown[]> {
    const q = new URLSearchParams();
    if (filters?.role) q.set("role", filters.role);
    if (filters?.phase) q.set("phase", filters.phase);
    const suffix = q.toString() ? `?${q}` : "";
    return j(`${BASE}/tasks/${taskId}/turns${suffix}`);
  },

  async postConversation(
    taskId: string,
    body: {
      role: string;
      message: string;
      referenced_node_ids: string[];
    },
  ): Promise<{ id: string; queue_depth: number; agent_turn_id?: string | null }> {
    return j(`${BASE}/tasks/${taskId}/conversations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },
};
