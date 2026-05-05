import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiClient } from "../api/client";
import { useOrchStore } from "../stores/orchStore";
import { SplitPanelLayout } from "../components/layout/SplitPanelLayout";
import { RolesTabBar } from "../components/roles/RolesTabBar";
import { RoleConversationPane } from "../components/roles/RoleConversationPane";
import {
  MindmapCanvas,
  type ApiEdge,
  type ApiNode,
} from "../components/MindmapCanvas";
import { useTaskWs } from "../hooks/useTaskWs";

function toApiNodes(raw: unknown[]): ApiNode[] {
  if (!Array.isArray(raw)) return [];
  const out: ApiNode[] = [];
  for (const x of raw) {
    if (!x || typeof x !== "object") continue;
    const o = x as Record<string, unknown>;
    const id = String(o.id ?? "").trim();
    if (!id) continue;
    out.push({
      id,
      kind: String(o.kind ?? "REQ"),
      title: String(o.title ?? ""),
      status:
        o.status != null && o.status !== "" ? String(o.status) : undefined,
    });
  }
  return out;
}

function toApiEdges(raw: unknown[]): ApiEdge[] {
  if (!Array.isArray(raw)) return [];
  const out: ApiEdge[] = [];
  for (const x of raw) {
    if (!x || typeof x !== "object") continue;
    const o = x as Record<string, unknown>;
    const id = String(o.id ?? "").trim();
    const from_id = String(o.from_id ?? "").trim();
    const to_id = String(o.to_id ?? "").trim();
    if (!id || !from_id || !to_id) continue;
    out.push({
      id,
      from_id,
      to_id,
      kind: String(o.kind ?? ""),
    });
  }
  return out;
}

export default function TaskDetailPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const [err, setErr] = useState<string | null>(null);
  const [auditOpen, setAuditOpen] = useState(false);
  const splitRatio = useOrchStore((s) => s.splitRatio);
  const setSplitRatio = useOrchStore((s) => s.setSplitRatio);
  const activeRoleTab = useOrchStore((s) => s.activeRoleTab);
  const setActiveRoleTab = useOrchStore((s) => s.setActiveRoleTab);
  const hydrateDetail = useOrchStore((s) => s.hydrateDetail);
  const detail = useOrchStore((s) => s.detail);
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(false);

  const refetchTask = useCallback(async () => {
    if (!taskId) return;
    try {
      const data = await apiClient.getTask(taskId);
      hydrateDetail(data as Record<string, unknown>);
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }, [taskId, hydrateDetail]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!taskId) return;
      try {
        const data = await apiClient.getTask(taskId);
        if (!cancelled)
          hydrateDetail(data as Record<string, unknown>);
      } catch (e) {
        if (!cancelled) setErr(e instanceof Error ? e.message : String(e));
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [taskId, hydrateDetail]);

  useTaskWs(taskId, (msg) => {
    if (
      msg.task_id !== taskId ||
      (msg.type !== "TurnAppended" && msg.type !== "GraphUpdated")
    )
      return;
    void refetchTask();
  });

  if (!taskId) return <p style={{ padding: 16 }}>无效的 task ID</p>;

  const taskTitle =
    detail.task ? String(detail.task.title ?? taskId) : "加载中…";
  const nodeCount = detail.nodes?.length ?? 0;
  const reposCount = detail.repos?.length ?? 0;

  const graphNodes = toApiNodes(detail.nodes);
  const graphEdges = toApiEdges(detail.edges);

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column" }}>
      <header
        style={{
          height: 48,
          flexShrink: 0,
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "0 12px",
          borderBottom: "1px solid #ddd",
          background: "#fff",
        }}
      >
        <Link to="/">← 返回</Link>
        <strong>{taskTitle}</strong>
        <span title="占位阶段条">●REQ ●G1 ●ARCH ○…</span>
        <button type="button" aria-label="关联仓库数量">
          Repos({reposCount})
        </button>
        <button type="button" onClick={() => setAuditOpen(true)}>
          全部 Turn
        </button>
      </header>
      <div style={{ flex: 1, minHeight: 0 }}>
        {err ? (
          <p style={{ color: "red", padding: 16 }}>{err}</p>
        ) : (
          <SplitPanelLayout
            ratio={splitRatio}
            onRatioChange={setSplitRatio}
            leftCollapsed={leftCollapsed}
            rightCollapsed={rightCollapsed}
            onToggleLeft={() => setLeftCollapsed((v) => !v)}
            onToggleRight={() => setRightCollapsed((v) => !v)}
            left={
              <div
                style={{
                  flex: 1,
                  minHeight: 0,
                  display: "flex",
                  flexDirection: "column",
                  background: "#f8fafc",
                  padding: 8,
                }}
              >
                <div style={{ flexShrink: 0, padding: "4px 8px", fontSize: 13 }}>
                  思维导图 · <strong>{nodeCount}</strong> 节点 ·{" "}
                  <strong>{graphEdges.length}</strong> 边
                </div>
                <div style={{ flex: 1, minHeight: 0 }}>
                  <MindmapCanvas nodes={graphNodes} edges={graphEdges} />
                </div>
              </div>
            }
            right={
              <>
                <RolesTabBar active={activeRoleTab} onChange={setActiveRoleTab} />
                <RoleConversationPane
                  taskId={taskId}
                  roleKey={activeRoleTab}
                  onAfterSend={refetchTask}
                />
              </>
            }
          />
        )}
      </div>
      {auditOpen ? (
        <TurnAuditModal taskId={taskId} onClose={() => setAuditOpen(false)} />
      ) : null}
    </div>
  );
}

function TurnAuditModal({
  taskId,
  onClose,
}: {
  taskId: string;
  onClose: () => void;
}) {
  const [loading, setLoading] = useState(true);
  const [turnErr, setTurnErr] = useState<string | null>(null);
  const [rows, setRows] = useState<unknown[]>([]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setTurnErr(null);
      try {
        const list = await apiClient.listTurns(taskId);
        if (!cancelled) setRows(list);
      } catch (e) {
        if (!cancelled)
          setTurnErr(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [taskId]);

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.4)",
        zIndex: 100,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div
        style={{
          background: "#fff",
          width: "90%",
          height: "85%",
          padding: 12,
          overflow: "auto",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexShrink: 0,
          }}
        >
          <strong>Turn 审计</strong>
          <button type="button" onClick={onClose}>
            关闭
          </button>
        </div>
        {loading ? (
          <p style={{ color: "#666" }}>加载中…</p>
        ) : turnErr ? (
          <p style={{ color: "red" }}>{turnErr}</p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0, margin: 0, flex: 1 }}>
            {rows.map((t, i) => (
              <TurnRow
                key={
                  t &&
                  typeof t === "object" &&
                  "id" in t &&
                  typeof (t as Record<string, unknown>).id === "string"
                    ? (t as Record<string, string>).id
                    : `idx-${i}`
                }
                turn={t}
                index={i}
              />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function TurnRow({ turn, index }: { turn: unknown; index: number }) {
  if (!turn || typeof turn !== "object") {
    return (
      <li style={{ borderBottom: "1px solid #eee", padding: 8 }}>
        #{index + 1} （无效数据）
      </li>
    );
  }
  const o = turn as Record<string, unknown>;
  const role = String(o.role ?? "");
  const adapter = String(o.adapter_name ?? "");
  const phase = String(o.phase ?? "");
  const out = String(o.output_text ?? "").slice(0, 280);
  return (
    <li
      style={{
        borderBottom: "1px solid #eee",
        padding: 8,
        fontSize: 13,
      }}
    >
      <strong>#{index + 1}</strong>{" "}
      <code>{role}</code>
      {adapter ? (
        <>
          {" "}
          · <small>{adapter}</small>
        </>
      ) : null}
      {phase ? (
        <>
          {" "}
          · <small>{phase}</small>
        </>
      ) : null}
      {out ? (
        <>
          {" "}
          — {out}
          {String(o.output_text ?? "").length > 280 ? "…" : ""}
        </>
      ) : null}
    </li>
  );
}
