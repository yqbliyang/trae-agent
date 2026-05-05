import { useEffect, useRef } from "react";

const HTTP = import.meta.env.VITE_ORCH_API ?? "http://127.0.0.1:8787";

export function orchWsUrl(taskId: string): string {
  return HTTP.replace(/^http/, "ws") + `/ws/tasks/${taskId}`;
}

export type WsPayload = { type: string; task_id: string; payload: unknown };

/** Subscribes to task WS; callback can change without reconnecting. */
export function useTaskWs(
  taskId: string | undefined,
  onMessage: (msg: WsPayload) => void,
): void {
  const cbRef = useRef(onMessage);
  cbRef.current = onMessage;

  useEffect(() => {
    if (!taskId) return;
    const ws = new WebSocket(orchWsUrl(taskId));
    ws.onmessage = (ev) => {
      try {
        cbRef.current(JSON.parse(ev.data) as WsPayload);
      } catch {
        /* ignore */
      }
    };
    return () => {
      ws.close();
    };
  }, [taskId]);
}
