import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TaskConfigDialog } from "../src/components/TaskConfigDialog";

describe("TaskConfigDialog", () => {
  it("blocks submit when title or root_requirement empty", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<TaskConfigDialog open onClose={() => {}} onSubmit={onSubmit} />);

    fireEvent.click(screen.getByText("创建"));

    expect(screen.getByText(/title 与 root_requirement 必填/i)).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("submits minimal payload without repos/max_rounds", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<TaskConfigDialog open onClose={() => {}} onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText(/标题/i), {
      target: { value: "t1" },
    });
    fireEvent.change(screen.getByLabelText(/根需求/i), {
      target: { value: "desc" },
    });
    fireEvent.click(screen.getByText("创建"));

    await vi.waitFor(() => expect(onSubmit).toHaveBeenCalledOnce());

    expect(onSubmit).toHaveBeenCalledWith({
      title: "t1",
      root_requirement: "desc",
      task_branch: null,
      ppe_lane: null,
    });
  });
});
