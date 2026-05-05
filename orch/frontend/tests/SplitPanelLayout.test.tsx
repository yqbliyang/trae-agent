import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SplitPanelLayout } from "../src/components/layout/SplitPanelLayout";

describe("SplitPanelLayout", () => {
  it("renders separator with role=separator", () => {
    render(
      <SplitPanelLayout
        ratio={0.5}
        onRatioChange={vi.fn()}
        leftCollapsed={false}
        rightCollapsed={false}
        onToggleLeft={vi.fn()}
        onToggleRight={vi.fn()}
        left={<div>left</div>}
        right={<div>right</div>}
      />,
    );
    expect(screen.getByRole("separator")).toHaveAttribute(
      "aria-orientation",
      "vertical",
    );
  });
});
