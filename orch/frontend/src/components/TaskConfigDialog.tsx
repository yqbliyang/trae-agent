import { FormEvent, useState } from "react";
import type { CreateTaskPayload } from "../../api/client";

export interface TaskConfigDialogProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (p: CreateTaskPayload) => Promise<void>;
}

export function TaskConfigDialog({ open, onClose, onSubmit }: TaskConfigDialogProps) {
  const [title, setTitle] = useState("");
  const [rootRequirement, setRootRequirement] = useState("");
  const [taskBranch, setTaskBranch] = useState("");
  const [ppeLane, setPpeLane] = useState("");
  const [err, setErr] = useState<string | null>(null);

  if (!open) return null;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    if (!title.trim() || !rootRequirement.trim()) {
      setErr("title 与 root_requirement 必填");
      return;
    }
    await onSubmit({
      title: title.trim(),
      root_requirement: rootRequirement.trim(),
      task_branch: taskBranch.trim() || null,
      ppe_lane: ppeLane.trim() || null,
    });
    setTitle("");
    setRootRequirement("");
    setTaskBranch("");
    setPpeLane("");
    onClose();
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.35)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 50,
      }}
      role="dialog"
      aria-modal="true"
    >
      <form
        onSubmit={submit}
        style={{
          background: "#fff",
          padding: 20,
          borderRadius: 10,
          width: 480,
          maxWidth: "90vw",
          display: "flex",
          flexDirection: "column",
          gap: 10,
        }}
      >
        <h2 style={{ marginTop: 0 }}>新建任务</h2>
        <label>
          标题 <span style={{ color: "red" }}>*</span>
          <input value={title} onChange={(e) => setTitle(e.target.value)} style={{ width: "100%" }} />
        </label>
        <label>
          根需求 <span style={{ color: "red" }}>*</span>
          <textarea
            rows={5}
            value={rootRequirement}
            onChange={(e) => setRootRequirement(e.target.value)}
            style={{ width: "100%" }}
            placeholder="背景、URL、仓库线索等…"
          />
        </label>
        <label>
          task_branch（可空，留空自动生成）
          <input
            value={taskBranch}
            onChange={(e) => setTaskBranch(e.target.value)}
            style={{ width: "100%" }}
            placeholder="orch/<task_id_short>/<slug>"
          />
        </label>
        <label>
          ppe_lane（可空）
          <input value={ppeLane} onChange={(e) => setPpeLane(e.target.value)} style={{ width: "100%" }} />
        </label>
        {err ? <p style={{ color: "red" }}>{err}</p> : null}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
          <button type="button" onClick={onClose}>
            取消
          </button>
          <button type="submit">创建</button>
        </div>
      </form>
    </div>
  );
}
