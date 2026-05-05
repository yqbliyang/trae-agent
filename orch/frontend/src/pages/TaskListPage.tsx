import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient } from "../api/client";
import { useOrchStore } from "../stores/orchStore";
import { TaskConfigDialog } from "../components/TaskConfigDialog";

export default function TaskListPage() {
  const [open, setOpen] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const setTaskList = useOrchStore((s) => s.setTaskList);

  const reload = async () => {
    setErr(null);
    try {
      const raw = await apiClient.listTasks();
      const mapped = raw.map((t) => {
        const obj = t as Record<string, unknown>;
        return { id: String(obj.id), title: String(obj.title), stage: String(obj.stage ?? "") };
      });
      setTaskList(mapped);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setTaskList([]);
    }
  };

  useEffect(() => {
    void reload();
  }, []);

  const tasks = useOrchStore((s) => s.taskList);

  return (
    <div style={{ padding: 16, maxWidth: 720, margin: "0 auto" }}>
      <h1>任务列表</h1>
      <p>
        <button type="button" onClick={() => setOpen(true)}>
          新建任务
        </button>
        &nbsp;
        <button type="button" onClick={() => reload()}>
          刷新
        </button>
      </p>
      {err ? <pre style={{ color: "brown" }}>{err}</pre> : null}
      <ul style={{ paddingLeft: 20 }}>
        {tasks.map((t) => (
          <li key={t.id}>
            <Link to={`/tasks/${t.id}`}>{t.title}</Link>{" "}
            <small style={{ color: "#777" }}>({t.stage || "?"})</small>
          </li>
        ))}
      </ul>

      <TaskConfigDialog
        open={open}
        onClose={() => setOpen(false)}
        onSubmit={async (p) => {
          await apiClient.createTask(p);
          await reload();
        }}
      />
    </div>
  );
}
