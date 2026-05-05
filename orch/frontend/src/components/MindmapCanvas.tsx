import { useCallback, useMemo } from "react";
import {
  Background,
  Controls,
  ReactFlow,
  type Edge as RFEdge,
  type Node as RFNode,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

/** API node shape from GET /tasks/{id} */
export interface ApiNode {
  id: string;
  kind: string;
  title: string;
  status?: string;
}

export interface ApiEdge {
  id: string;
  from_id: string;
  to_id: string;
  kind: string;
}

const COL = { REQ: 0, ARCH: 220, CODE: 440, TEST: 660 };

function layoutNodes(nodes: ApiNode[]): RFNode[] {
  const byKind: Record<string, ApiNode[]> = {};
  for (const n of nodes) {
    const k = n.kind || "REQ";
    (byKind[k] ??= []).push(n);
  }
  const out: RFNode[] = [];
  for (const [kind, list] of Object.entries(byKind)) {
    const x = COL[kind as keyof typeof COL] ?? 80;
    list.forEach((n, i) => {
      out.push({
        id: n.id,
        position: { x, y: i * 90 },
        data: { label: `${n.kind} ${n.title}`.trim() },
        draggable: false,
        selectable: true,
      });
    });
  }
  return out;
}

function toRfEdges(edges: ApiEdge[]): RFEdge[] {
  return edges.map((e) => ({
    id: e.id,
    source: e.from_id,
    target: e.to_id,
    label: e.kind,
  }));
}

export interface MindmapCanvasProps {
  nodes: ApiNode[];
  edges: ApiEdge[];
  onNodeClick?: (nodeId: string) => void;
}

export function MindmapCanvas({
  nodes,
  edges,
  onNodeClick,
}: MindmapCanvasProps) {
  const rfNodes = useMemo(() => layoutNodes(nodes), [nodes]);
  const rfEdges = useMemo(() => toRfEdges(edges), [edges]);

  const handleClick = useCallback(
    (_: unknown, n: RFNode) => {
      onNodeClick?.(n.id);
    },
    [onNodeClick],
  );

  return (
    <div style={{ width: "100%", height: "100%", minHeight: 320 }}>
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        fitView
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        onNodeClick={handleClick}
        proOptions={{ hideAttribution: true }}
      >
        <Background />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
