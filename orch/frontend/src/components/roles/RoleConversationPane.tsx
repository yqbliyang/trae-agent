import { FormEvent, useState } from "react";
import type { RoleTab } from "../../stores/orchStore";
import { apiClient } from "../../api/client";

export function RoleConversationPane({
  taskId,
  roleKey,
  onAfterSend,
}: {
  taskId: string;
  roleKey: RoleTab;
  onAfterSend?: () => void;
}) {
  const [text, setText] = useState("");
  const [status, setStatus] = useState<string | null>(null);

  const send = async (e: FormEvent) => {
    e.preventDefault();
    if (!text.trim()) return;
    setStatus("发送中...");
    try {
      const r = await apiClient.postConversation(taskId, {
        role: roleKey,
        message: text.trim(),
        referenced_node_ids: [],
      });
      setStatus(
        `排队深度: ${r.queue_depth}` +
          (r.agent_turn_id ? ` · agent turn: ${r.agent_turn_id}` : ""),
      );
      setText("");
      onAfterSend?.();
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "失败");
    }
  };

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", padding: 8 }}>
      <p style={{ color: "#666", fontSize: 13 }}>
        与角色 <code>{roleKey}</code> 对话（占位 UI；服务端入队）。
      </p>
      <form onSubmit={send} style={{ marginTop: "auto", display: "flex", gap: 8 }}>
        <input
          style={{ flex: 1 }}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="输入消息…"
          aria-label="消息"
        />
        <button type="submit">发送</button>
      </form>
      {status ? <small style={{ color: "#444" }}>{status}</small> : null}
    </div>
  );
}
