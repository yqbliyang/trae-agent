import { Navigate, Route, Routes } from "react-router-dom";
import "./index.css";
import TaskDetailPage from "./pages/TaskDetailPage";
import TaskListPage from "./pages/TaskListPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<TaskListPage />} />
      <Route path="/tasks/:taskId" element={<TaskDetailPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
