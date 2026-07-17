"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { capture } from "@/lib/analytics";
import {
  DEFAULT_PARAMS,
  initialPositions,
  stepSimulation,
  type SimEdge,
  type SimNode,
  type SimParams,
} from "@/lib/graph-layout";
import type { ConvergenceGraph } from "@/lib/types";
import { entityDisplayName } from "@/lib/entities";
import { cn } from "@/lib/utils";

const W = 800;
const H = 600;
const MAX_FRAMES = 600;
const SETTLE_ENERGY = 4;

const DESK_COLOR: Record<string, string> = {
  defense: "#dc2626",
  ai: "#2563eb",
  energy: "#16a34a",
};
const CONVERGENCE_COLOR = "#9333ea"; // spans ≥2 desks — the star of the show

function nodeColor(desks: string[]): string {
  if (desks.length >= 2) return CONVERGENCE_COLOR;
  return DESK_COLOR[desks[0]] ?? "#64748b";
}

export function ConvergenceGraph({ graph }: { graph: ConvergenceGraph }) {
  const router = useRouter();
  const [crossDeskOnly, setCrossDeskOnly] = useState(false);
  const [minConf, setMinConf] = useState(0);
  const [hovered, setHovered] = useState<string | null>(null);

  // Fire the view event once — the behavioral read on whether the hero surface gets explored.
  useEffect(() => {
    capture({
      name: "convergence_graph_viewed",
      node_count: graph.meta.node_count,
      edge_count: graph.meta.edge_count,
      cross_desk_edges: graph.meta.cross_desk_edges,
    });
  }, [graph.meta]);

  // Client-side filters (the graph is small; no refetch needed).
  const { visibleNodes, simEdges, degree } = useMemo(() => {
    const edges = graph.edges.filter(
      (e) => (!crossDeskOnly || e.cross_desk) && e.confidence >= minConf,
    );
    const ids = new Set<string>();
    const deg: Record<string, number> = {};
    for (const e of edges) {
      ids.add(e.from);
      ids.add(e.to);
      deg[e.from] = (deg[e.from] ?? 0) + 1;
      deg[e.to] = (deg[e.to] ?? 0) + 1;
    }
    return {
      visibleNodes: graph.nodes.filter((n) => ids.has(n.id)),
      simEdges: edges.map((e): SimEdge & { cross_desk: boolean; confidence: number } => ({
        from: e.from,
        to: e.to,
        weight: e.weight,
        cross_desk: e.cross_desk,
        confidence: e.confidence,
      })),
      degree: deg,
    };
  }, [graph, crossDeskOnly, minConf]);

  const nodeById = useMemo(
    () => new Map(visibleNodes.map((n) => [n.id, n])),
    [visibleNodes],
  );
  const neighbors = useMemo(() => {
    const m = new Map<string, Set<string>>();
    for (const e of simEdges) {
      (m.get(e.from) ?? m.set(e.from, new Set()).get(e.from)!).add(e.to);
      (m.get(e.to) ?? m.set(e.to, new Set()).get(e.to)!).add(e.from);
    }
    return m;
  }, [simEdges]);

  const params: SimParams = { width: W, height: H, ...DEFAULT_PARAMS };

  // Simulation state lives in a ref (authoritative); render state is a copy set each frame.
  const nodesRef = useRef<SimNode[]>([]);
  const [renderNodes, setRenderNodes] = useState<SimNode[]>([]);
  const pinnedRef = useRef<Set<string>>(new Set());
  const rafRef = useRef<number | null>(null);
  const runningRef = useRef(false);
  const svgRef = useRef<SVGSVGElement>(null);

  const startLoop = useCallback(() => {
    if (runningRef.current) return;
    runningRef.current = true;
    let frames = 0;
    const loop = () => {
      nodesRef.current = stepSimulation(nodesRef.current, simEdges, params, pinnedRef.current);
      const energy = nodesRef.current.reduce((s, n) => s + Math.hypot(n.vx, n.vy), 0);
      setRenderNodes(nodesRef.current);
      frames += 1;
      if (frames < MAX_FRAMES && (energy > SETTLE_ENERGY || pinnedRef.current.size > 0)) {
        rafRef.current = requestAnimationFrame(loop);
      } else {
        runningRef.current = false;
      }
    };
    rafRef.current = requestAnimationFrame(loop);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [simEdges]);

  // (Re)initialize the layout whenever the visible node set changes.
  const layoutKey = visibleNodes.map((n) => n.id).sort().join(",");
  useEffect(() => {
    nodesRef.current = initialPositions(
      visibleNodes.map((n) => n.id),
      W,
      H,
    );
    setRenderNodes(nodesRef.current);
    pinnedRef.current = new Set();
    runningRef.current = false;
    startLoop();
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layoutKey]);

  // ── pointer: drag a node, or click through to its Entity 360 ──
  const dragRef = useRef<{ id: string; moved: boolean } | null>(null);

  function toSvg(clientX: number, clientY: number) {
    const rect = svgRef.current!.getBoundingClientRect();
    return {
      x: ((clientX - rect.left) / rect.width) * W,
      y: ((clientY - rect.top) / rect.height) * H,
    };
  }

  function onNodePointerDown(e: React.PointerEvent, id: string) {
    e.stopPropagation();
    (e.target as Element).setPointerCapture(e.pointerId);
    dragRef.current = { id, moved: false };
    pinnedRef.current.add(id);
    startLoop();
  }

  function onPointerMove(e: React.PointerEvent) {
    const drag = dragRef.current;
    if (!drag) return;
    const { x, y } = toSvg(e.clientX, e.clientY);
    dragRef.current = { ...drag, moved: true };
    nodesRef.current = nodesRef.current.map((n) =>
      n.id === drag.id ? { ...n, x, y, vx: 0, vy: 0 } : n,
    );
    setRenderNodes(nodesRef.current);
    startLoop();
  }

  function onPointerUp(id: string) {
    const drag = dragRef.current;
    pinnedRef.current.delete(id);
    dragRef.current = null;
    startLoop();
    if (drag && !drag.moved) {
      const node = nodeById.get(id);
      capture({ name: "convergence_node_clicked", entity_id: id, convergence: node?.convergence ?? false });
      router.push(`/entity/${id}`);
    }
  }

  const activeIds = useMemo(() => {
    if (!hovered) return null;
    const set = new Set<string>([hovered]);
    for (const nb of neighbors.get(hovered) ?? []) set.add(nb);
    return set;
  }, [hovered, neighbors]);

  const pos = useMemo(() => new Map(renderNodes.map((n) => [n.id, n])), [renderNodes]);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-4 text-sm">
        <label className="flex items-center gap-2 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={crossDeskOnly}
            onChange={(e) => setCrossDeskOnly(e.target.checked)}
            className="accent-[var(--color-brand,#9333ea)]"
          />
          Cross-desk only
        </label>
        <label className="flex items-center gap-2">
          <span className="text-muted-foreground">Min confidence</span>
          <input
            type="range"
            min={0}
            max={0.95}
            step={0.05}
            value={minConf}
            onChange={(e) => setMinConf(Number(e.target.value))}
          />
          <span className="tabular-nums w-8 text-muted-foreground">{minConf.toFixed(2)}</span>
        </label>
        <span className="ml-auto text-muted-foreground">
          {visibleNodes.length} entities · {simEdges.length} links
        </span>
      </div>

      <div className="rounded-lg border border-border bg-card">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          className="w-full h-auto touch-none"
          onPointerMove={onPointerMove}
          role="img"
          aria-label="Convergence graph: entities that recur together across the Defense, AI, and Energy desks"
        >
          {simEdges.map((e, i) => {
            const a = pos.get(e.from);
            const b = pos.get(e.to);
            if (!a || !b) return null;
            const dim = activeIds && !(activeIds.has(e.from) && activeIds.has(e.to));
            return (
              <line
                key={i}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke={e.cross_desk ? CONVERGENCE_COLOR : "#94a3b8"}
                strokeWidth={Math.max(1, Math.min(6, e.weight))}
                strokeOpacity={dim ? 0.08 : 0.25 + e.confidence * 0.5}
              />
            );
          })}
          {renderNodes.map((n) => {
            const meta = nodeById.get(n.id);
            if (!meta) return null;
            const r = Math.min(20, 7 + (degree[n.id] ?? 0) * 2);
            const dim = activeIds && !activeIds.has(n.id);
            const showLabel = meta.convergence || hovered === n.id || (degree[n.id] ?? 0) >= 3;
            return (
              <g
                key={n.id}
                transform={`translate(${n.x},${n.y})`}
                className="cursor-pointer"
                opacity={dim ? 0.2 : 1}
                onPointerDown={(e) => onNodePointerDown(e, n.id)}
                onPointerUp={() => onPointerUp(n.id)}
                onPointerEnter={() => setHovered(n.id)}
                onPointerLeave={() => setHovered((h) => (h === n.id ? null : h))}
              >
                <circle
                  r={r}
                  fill={nodeColor(meta.desks)}
                  fillOpacity={0.85}
                  stroke="var(--color-background,#fff)"
                  strokeWidth={1.5}
                />
                {showLabel && (
                  <text
                    y={-r - 5}
                    textAnchor="middle"
                    className="pointer-events-none fill-foreground"
                    style={{ fontSize: 12, fontWeight: meta.convergence ? 600 : 400 }}
                  >
                    {meta.ticker ?? entityDisplayName(meta.name)}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>

      <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
        <LegendDot color={CONVERGENCE_COLOR} label="Cross-desk (convergence)" />
        <LegendDot color={DESK_COLOR.defense} label="Defense" />
        <LegendDot color={DESK_COLOR.ai} label="AI" />
        <LegendDot color={DESK_COLOR.energy} label="Energy" />
        <span className="ml-auto">Drag to rearrange · click a node for its Entity 360</span>
      </div>
    </div>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className={cn("inline-block h-2.5 w-2.5 rounded-full")} style={{ backgroundColor: color }} />
      {label}
    </span>
  );
}
