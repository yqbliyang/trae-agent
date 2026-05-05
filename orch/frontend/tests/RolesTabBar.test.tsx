import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RolesTabBar } from "../src/components/roles/RolesTabBar";

describe("RolesTabBar", () => {
  it("fires onChange when tab clicked", () => {
    const onChange = vi.fn();
    render(
      <RolesTabBar active="arch_designer" onChange={onChange} />,
    );
    fireEvent.click(screen.getByText("REQ拆分"));
    expect(onChange).toHaveBeenCalledWith("req_decomposer");
  });

  it("disables + expansion slot", () => {
    render(<RolesTabBar active="arch_designer" onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: "+" })).toBeDisabled();
  });
});
