import type { ReactNode } from "react";
import { useCallback, useEffect, useRef } from "react";

const MIN_PX = 320;
export const SPLIT_COLLAPSED_PX = 48;

export interface SplitPanelLayoutProps {
  ratio: number;
  onRatioChange: (r: number) => void;
  leftCollapsed: boolean;
  rightCollapsed: boolean;
  onToggleLeft: () => void;
  onToggleRight: () => void;
  left: ReactNode;
  right: ReactNode;
}

export function SplitPanelLayout({
  ratio,
  onRatioChange,
  leftCollapsed,
  rightCollapsed,
  onToggleLeft,
  onToggleRight,
  left,
  right,
}: SplitPanelLayoutProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const drag = useRef(false);

  const onMove = useCallback(
    (e: MouseEvent) => {
      if (!drag.current || !containerRef.current) return;
      if (leftCollapsed || rightCollapsed) return;
      const rect = containerRef.current.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const r = Math.min(0.85, Math.max(0.15, x / rect.width));
      onRatioChange(r);
    },
    [onRatioChange, leftCollapsed, rightCollapsed],
  );

  useEffect(() => {
    window.addEventListener("mousemove", onMove);
    const up = () => {
      drag.current = false;
    };
    window.addEventListener("mouseup", up);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", up);
    };
  }, [onMove]);

  const lStyle = leftCollapsed
    ? ({ flex: `0 0 ${SPLIT_COLLAPSED_PX}px` } as const)
    : ({ flexGrow: ratio * 1000, flexShrink: 1, flexBasis: 0, minWidth: MIN_PX } as const);
  const rStyle = rightCollapsed
    ? ({ flex: `0 0 ${SPLIT_COLLAPSED_PX}px` } as const)
    : ({
        flexGrow: (1 - ratio) * 1000,
        flexShrink: 1,
        flexBasis: 0,
        minWidth: MIN_PX,
      } as const);

  return (
    <div
      ref={containerRef}
      style={{
        display: "flex",
        height: "100%",
        width: "100%",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          ...lStyle,
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
        }}
      >
        {left}
      </div>
      <div
        role="separator"
        aria-orientation="vertical"
        onMouseDown={() => {
          if (!leftCollapsed && !rightCollapsed) drag.current = true;
        }}
        style={{
          width: 6,
          background: "#e0e0e0",
          cursor: leftCollapsed || rightCollapsed ? "default" : "col-resize",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 6,
          flexShrink: 0,
        }}
      >
        <button type="button" aria-label="折叠左栏" onClick={onToggleLeft}>
          ◀
        </button>
        <button type="button" aria-label="折叠右栏" onClick={onToggleRight}>
          ▶
        </button>
      </div>
      <div
        style={{
          ...rStyle,
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
        }}
      >
        {right}
      </div>
    </div>
  );
}
