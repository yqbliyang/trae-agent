import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiClient } from "../api/client";
import { useOrchStore } from "../stores/orchStore";
import { SplitPanelLayout } from "../components/layout/SplitPanelLayout";
import { RolesTabBar } from "../components/roles/RolesTabBar";
import { RoleConversationPane } from "../components/roles/RoleConversationPane";

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

  if (!taskId) return <p style={{ padding: 16 }}>无效的 task ID</p>;

  const taskTitle =
    detail.task ? String(detail.task.title ?? taskId) : "加载中…";
  const nodeCount = detail.nodes?.length ?? 0;

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
        <button type="button" aria-label="仓库占位">
          Repos(0)
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
              <div style={{ flex: 1, background: "#f0f9ff", padding: 16 }}>
                <strong>MindmapCanvas</strong>（占位）— 节点数 {nodeCount}
              </div>
            }
            right={
              <>
                <RolesTabBar active={activeRoleTab} onChange={setActiveRoleTab} />
                <RoleConversationPane taskId={taskId} roleKey={activeRoleTab} />
              </>
            }
          />
        )}
      </div>
      {auditOpen ? (
        <TurnAuditPlaceholder onClose={() => setAuditOpen(false)} />
      ) : null}
    </div>
  );
}

function TurnAuditPlaceholder({ onClose }: { onClose: () => void }) {
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
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <strong>TurnAuditModal（占位）</strong>
          <button type="button" onClick={onClose}>
            关闭
          </button>
        </div>
        <p>GET /tasks/&#123;id&#125;/turns</p>
      </div>
    </div>
  );
}
