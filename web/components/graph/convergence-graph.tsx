"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { capture } from "@/lib/analytics";
import {
  DEFAULT_PARAMS,
  initialPositions,
  stepSimulation,
  type SimNode,
  type SimParams,
} from "@/lib/graph-layout";
import type { ConvergenceGraph, EdgeCoappearances } from "@/lib/types";
import { deskLabel, entityDisplayName } from "@/lib/entities";
import { cn } from "@/lib/utils";

const W = 960;
const H = 640;
const MAX_FRAMES = 600;
const SETTLE_ENERGY = 4;

// On-brand palette (DESIGN_SYSTEM.md): desk accents + antique gold for convergence.
const DESK: Record<string, { base: string; glow: string }> = {
  defense: { base: "#1b3a6b", glow: "#3a5c93" },
  ai: { base: "#7c3aed", glow: "#9d6bf6" },
  energy: { base: "#16a34a", glow: "#3ccb6e" },
};
const GOLD = { base: "#c8a96e", glow: "#e6cf9a" };
const NEUTRAL = { base: "#8a8a82", glow: "#a8a8a0" };

function paletteKey(desks: string[]): string {
  if (desks.length >= 2) return "gold";
  return DESK[desks[0]] ? desks[0] : "neutral";
}
function palette(key: string) {
  if (key === "gold") return GOLD;
  return DESK[key] ?? NEUTRAL;
}

type RenderEdge = {
  from: string;
  to: string;
  weight: number;
  cross_desk: boolean;
  confidence: number;
  co_count: number;
  desks: string[];
};

export function ConvergenceGraph({ graph }: { graph: ConvergenceGraph }) {
  const router = useRouter();
  const [crossDeskOnly, setCrossDeskOnly] = useState(false);
  const [minConf, setMinConf] = useState(0);
  const [hovered, setHovered] = useState<string | null>(null);
  const [hoveredEdge, setHoveredEdge] = useState<RenderEdge | null>(null);

  useEffect(() => {
    capture({
      name: "convergence_graph_viewed",
      node_count: graph.meta.node_count,
      edge_count: graph.meta.edge_count,
      cross_desk_edges: graph.meta.cross_desk_edges,
    });
  }, [graph.meta]);

  const { visibleNodes, simEdges, degree } = useMemo(() => {
    const edges: RenderEdge[] = graph.edges
      .filter((e) => (!crossDeskOnly || e.cross_desk) && e.confidence >= minConf)
      .map((e) => ({
        from: e.from,
        to: e.to,
        weight: e.weight,
        cross_desk: e.cross_desk,
        confidence: e.confidence,
        co_count: e.co_count,
        desks: e.desks,
      }));
    const ids = new Set<string>();
    const deg: Record<string, number> = {};
    for (const e of edges) {
      ids.add(e.from);
      ids.add(e.to);
      deg[e.from] = (deg[e.from] ?? 0) + 1;
      deg[e.to] = (deg[e.to] ?? 0) + 1;
    }
    return { visibleNodes: graph.nodes.filter((n) => ids.has(n.id)), simEdges: edges, degree: deg };
  }, [graph, crossDeskOnly, minConf]);

  const nodeById = useMemo(() => new Map(visibleNodes.map((n) => [n.id, n])), [visibleNodes]);
  const colorOf = useCallback(
    (id: string) => palette(paletteKey(nodeById.get(id)?.desks ?? [])).base,
    [nodeById],
  );
  const labelOf = useCallback(
    (id: string) => {
      const n = nodeById.get(id);
      return n ? (n.ticker ?? entityDisplayName(n.name)) : "";
    },
    [nodeById],
  );
  const neighbors = useMemo(() => {
    const m = new Map<string, Set<string>>();
    const add = (a: string, b: string) => {
      if (!m.has(a)) m.set(a, new Set());
      m.get(a)!.add(b);
    };
    for (const e of simEdges) {
      add(e.from, e.to);
      add(e.to, e.from);
    }
    return m;
  }, [simEdges]);

  const params: SimParams = { width: W, height: H, ...DEFAULT_PARAMS };

  const nodesRef = useRef<SimNode[]>([]);
  const [renderNodes, setRenderNodes] = useState<SimNode[]>([]);
  const pinnedRef = useRef<Set<string>>(new Set());
  const rafRef = useRef<number | null>(null);
  const runningRef = useRef(false);
  const svgRef = useRef<SVGSVGElement>(null);
  const simEdgesRef = useRef(simEdges);
  simEdgesRef.current = simEdges;

  const startLoop = useCallback(() => {
    if (runningRef.current) return;
    runningRef.current = true;
    let frames = 0;
    const loop = () => {
      nodesRef.current = stepSimulation(nodesRef.current, simEdgesRef.current, params, pinnedRef.current);
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
  }, []);

  const layoutKey = visibleNodes.map((n) => n.id).sort().join(",");
  useEffect(() => {
    nodesRef.current = initialPositions(visibleNodes.map((n) => n.id), W, H);
    setRenderNodes(nodesRef.current);
    pinnedRef.current = new Set();
    runningRef.current = false;
    startLoop();
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layoutKey]);

  // ── edge evidence: fetch the shared stories on hover (cached per pair) ──
  const [edgeStories, setEdgeStories] = useState<EdgeCoappearances | null>(null);
  const [edgeLoading, setEdgeLoading] = useState(false);
  const storyCache = useRef<Map<string, EdgeCoappearances>>(new Map());
  useEffect(() => {
    if (!hoveredEdge) {
      setEdgeStories(null);
      setEdgeLoading(false);
      return;
    }
    const key = `${hoveredEdge.from}|${hoveredEdge.to}`;
    const cached = storyCache.current.get(key);
    if (cached) {
      setEdgeStories(cached);
      setEdgeLoading(false);
      return;
    }
    let cancelled = false;
    setEdgeStories(null);
    setEdgeLoading(true);
    fetch(`/api/graph/co-appearances?a=${hoveredEdge.from}&b=${hoveredEdge.to}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d: EdgeCoappearances | null) => {
        if (cancelled) return;
        if (d) {
          storyCache.current.set(key, d);
          setEdgeStories(d);
        }
        setEdgeLoading(false);
      })
      .catch(() => !cancelled && setEdgeLoading(false));
    return () => {
      cancelled = true;
    };
  }, [hoveredEdge]);

  // ── pointer: drag a node, or click through to its Entity 360 ──
  const dragRef = useRef<{ id: string; moved: boolean } | null>(null);
  function toSvg(clientX: number, clientY: number) {
    const rect = svgRef.current!.getBoundingClientRect();
    return { x: ((clientX - rect.left) / rect.width) * W, y: ((clientY - rect.top) / rect.height) * H };
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
    nodesRef.current = nodesRef.current.map((n) => (n.id === drag.id ? { ...n, x, y, vx: 0, vy: 0 } : n));
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
    if (hovered) {
      const set = new Set<string>([hovered]);
      for (const nb of neighbors.get(hovered) ?? []) set.add(nb);
      return set;
    }
    if (hoveredEdge) return new Set<string>([hoveredEdge.from, hoveredEdge.to]);
    return null;
  }, [hovered, hoveredEdge, neighbors]);

  const pos = useMemo(() => new Map(renderNodes.map((n) => [n.id, n])), [renderNodes]);
  const hoveredNode = hovered ? nodeById.get(hovered) : null;
  const hoveredNodePos = hovered ? pos.get(hovered) : null;
  const edgeMid = hoveredEdge
    ? (() => {
        const a = pos.get(hoveredEdge.from);
        const b = pos.get(hoveredEdge.to);
        return a && b ? { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 } : null;
      })()
    : null;

  const isHoveredEdge = (e: RenderEdge) =>
    hoveredEdge != null && hoveredEdge.from === e.from && hoveredEdge.to === e.to;

  return (
    <div className="flex flex-col gap-4">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3 rounded-lg border border-border bg-card px-4 py-2.5 text-ui-sm">
        <label className="flex cursor-pointer select-none items-center gap-2 font-medium">
          <input
            type="checkbox"
            checked={crossDeskOnly}
            onChange={(e) => setCrossDeskOnly(e.target.checked)}
            className="h-3.5 w-3.5 accent-[#c8a96e]"
          />
          Cross-desk only
        </label>
        <label className="flex items-center gap-2.5">
          <span className="text-muted-foreground">Min confidence</span>
          <input
            type="range"
            min={0}
            max={0.95}
            step={0.05}
            value={minConf}
            onChange={(e) => setMinConf(Number(e.target.value))}
            className="w-28 accent-[#1b3a6b]"
          />
          <span className="w-8 tabular-nums text-muted-foreground">{minConf.toFixed(2)}</span>
        </label>
        <span className="ml-auto text-muted-foreground">
          <span className="font-medium text-foreground tabular-nums">{visibleNodes.length}</span> entities
          <span className="mx-1.5 text-border">·</span>
          <span className="font-medium text-foreground tabular-nums">{simEdges.length}</span> links
        </span>
      </div>

      {/* Canvas */}
      <div
        className="relative overflow-hidden rounded-xl border border-border"
        style={{ background: "radial-gradient(120% 130% at 50% 0%, #ffffff 0%, #f6f5f1 62%, #f1efe9 100%)" }}
      >
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          className="h-auto w-full touch-none animate-fade-in"
          onPointerMove={onPointerMove}
          role="img"
          aria-label="Convergence graph: entities that recur together across the Defense, AI, and Energy desks"
        >
          <defs>
            {(["defense", "ai", "energy", "gold", "neutral"] as const).map((k) => {
              const c = palette(k);
              return (
                <radialGradient key={k} id={`nodefill-${k}`} cx="38%" cy="34%" r="72%">
                  <stop offset="0%" stopColor={c.glow} />
                  <stop offset="100%" stopColor={c.base} />
                </radialGradient>
              );
            })}
            <filter id="node-glow" x="-60%" y="-60%" width="220%" height="220%">
              <feGaussianBlur stdDeviation="6" result="b" />
              <feMerge>
                <feMergeNode in="b" />
              </feMerge>
            </filter>
            {simEdges.map((e, i) => {
              const a = pos.get(e.from);
              const b = pos.get(e.to);
              if (!a || !b) return null;
              return (
                <linearGradient
                  key={i}
                  id={`edge-${i}`}
                  gradientUnits="userSpaceOnUse"
                  x1={a.x}
                  y1={a.y}
                  x2={b.x}
                  y2={b.y}
                >
                  <stop offset="0%" stopColor={colorOf(e.from)} />
                  <stop offset="100%" stopColor={colorOf(e.to)} />
                </linearGradient>
              );
            })}
          </defs>

          {/* Edges — curved, gradient-blended (sector A meeting sector B) */}
          <g strokeLinecap="round" fill="none">
            {simEdges.map((e, i) => {
              const a = pos.get(e.from);
              const b = pos.get(e.to);
              if (!a || !b) return null;
              const dim = activeIds && !(activeIds.has(e.from) && activeIds.has(e.to));
              const hot = isHoveredEdge(e);
              const mx = (a.x + b.x) / 2;
              const my = (a.y + b.y) / 2;
              const cx = mx - (b.y - a.y) * 0.12;
              const cy = my + (b.x - a.x) * 0.12;
              const d = `M${a.x},${a.y} Q${cx},${cy} ${b.x},${b.y}`;
              return (
                <g key={i}>
                  <path
                    d={d}
                    stroke={`url(#edge-${i})`}
                    strokeWidth={hot ? Math.max(2.4, Math.min(6, e.weight + 1.5)) : Math.max(1.2, Math.min(5, e.weight))}
                    strokeOpacity={dim ? 0.06 : hot ? 0.95 : 0.22 + e.confidence * 0.5}
                    style={{ transition: "stroke-opacity 150ms ease, stroke-width 150ms ease" }}
                  />
                  {/* wide invisible hit area for reliable hover */}
                  <path
                    d={d}
                    stroke="transparent"
                    strokeWidth={16}
                    className="cursor-help"
                    style={{ pointerEvents: "stroke" }}
                    onPointerEnter={() => {
                      setHoveredEdge(e);
                      setHovered(null);
                    }}
                    onPointerLeave={() => setHoveredEdge((cur) => (cur === e ? null : cur))}
                  />
                </g>
              );
            })}
          </g>

          {/* Nodes */}
          <g>
            {renderNodes.map((n) => {
              const meta = nodeById.get(n.id);
              if (!meta) return null;
              const key = paletteKey(meta.desks);
              const c = palette(key);
              const isConv = meta.convergence;
              const r = Math.min(24, 8 + Math.sqrt(degree[n.id] ?? 0) * 3.2) + (isConv ? 2 : 0);
              const dim = activeIds && !activeIds.has(n.id);
              const focus = hovered === n.id;
              const showLabel = isConv || focus || (degree[n.id] ?? 0) >= 3;
              return (
                <g
                  key={n.id}
                  transform={`translate(${n.x},${n.y})`}
                  className="cursor-pointer"
                  style={{ opacity: dim ? 0.22 : 1, transition: "opacity 200ms ease" }}
                  onPointerDown={(e) => onNodePointerDown(e, n.id)}
                  onPointerUp={() => onPointerUp(n.id)}
                  onPointerEnter={() => {
                    setHovered(n.id);
                    setHoveredEdge(null);
                  }}
                  onPointerLeave={() => setHovered((h) => (h === n.id ? null : h))}
                >
                  {(isConv || focus) && (
                    <circle r={r + 6} fill={c.glow} opacity={focus ? 0.5 : 0.32} filter="url(#node-glow)" />
                  )}
                  <circle
                    r={r}
                    fill={`url(#nodefill-${key})`}
                    stroke={focus ? c.base : "#ffffff"}
                    strokeWidth={focus ? 2 : 1.5}
                  />
                  {isConv && <circle r={r} fill="none" stroke={GOLD.base} strokeOpacity={0.55} strokeWidth={1} />}
                  {showLabel && (
                    <text
                      y={-r - 7}
                      textAnchor="middle"
                      className="pointer-events-none select-none"
                      style={{
                        font: `${isConv ? 600 : 500} 12px var(--font-ui, Inter), system-ui, sans-serif`,
                        fill: "#1a1a1a",
                        paintOrder: "stroke",
                        stroke: "#faf9f7",
                        strokeWidth: 3,
                        strokeLinejoin: "round",
                        letterSpacing: "-0.01em",
                      }}
                    >
                      {meta.ticker ?? entityDisplayName(meta.name)}
                    </text>
                  )}
                </g>
              );
            })}
          </g>
        </svg>

        {/* Node hover card */}
        {hoveredNode && hoveredNodePos && !hoveredEdge && (
          <div
            className="pointer-events-none absolute z-10 w-max max-w-xs -translate-x-1/2 rounded-lg border border-border bg-popover px-3.5 py-2.5 shadow-lg"
            style={{
              left: `${(hoveredNodePos.x / W) * 100}%`,
              top: `${(hoveredNodePos.y / H) * 100}%`,
              transform: "translate(-50%, calc(-100% - 18px))",
            }}
          >
            <div className="font-display text-base font-semibold leading-tight text-foreground">
              {entityDisplayName(hoveredNode.name)}
            </div>
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
              {hoveredNode.ticker ? (
                <span className="rounded bg-secondary px-1.5 py-0.5 text-ui-xs font-semibold tabular-nums text-foreground">
                  {hoveredNode.ticker}
                </span>
              ) : (
                <span className="rounded bg-secondary px-1.5 py-0.5 text-ui-xs text-muted-foreground">
                  private / venture
                </span>
              )}
              {hoveredNode.desks.map((d) => (
                <span
                  key={d}
                  className="rounded px-1.5 py-0.5 text-ui-xs font-medium text-white"
                  style={{ backgroundColor: (DESK[d] ?? NEUTRAL).base }}
                >
                  {deskLabel(d)}
                </span>
              ))}
            </div>
            {hoveredNode.convergence && (
              <div className="mt-1.5 text-ui-xs font-medium" style={{ color: GOLD.base }}>
                Converges across {hoveredNode.desks.length} desks
              </div>
            )}
          </div>
        )}

        {/* Edge hover card — the evidence behind a connection */}
        {hoveredEdge && edgeMid && (
          <div
            className="pointer-events-none absolute z-10 w-72 -translate-x-1/2 rounded-lg border border-border bg-popover px-3.5 py-2.5 shadow-lg"
            style={{
              left: `${Math.min(88, Math.max(12, (edgeMid.x / W) * 100))}%`,
              top: `${(edgeMid.y / H) * 100}%`,
              transform: "translate(-50%, calc(-100% - 14px))",
            }}
          >
            <div className="flex items-center justify-center gap-2 text-ui-sm font-semibold text-foreground">
              <span className="tabular-nums">{labelOf(hoveredEdge.from)}</span>
              <span className="text-muted-foreground">⇄</span>
              <span className="tabular-nums">{labelOf(hoveredEdge.to)}</span>
            </div>
            <div className="mt-1.5 flex flex-wrap items-center justify-center gap-1.5 text-ui-xs text-muted-foreground">
              {hoveredEdge.desks.map((d) => (
                <span
                  key={d}
                  className="rounded px-1.5 py-0.5 font-medium text-white"
                  style={{ backgroundColor: (DESK[d] ?? NEUTRAL).base }}
                >
                  {deskLabel(d)}
                </span>
              ))}
              <span>
                co-appeared {hoveredEdge.co_count}× · {Math.round(hoveredEdge.confidence * 100)}% confidence
              </span>
            </div>
            <div className="mt-2 border-t border-border pt-2">
              {edgeLoading && <div className="text-ui-xs italic text-muted-foreground">Loading stories…</div>}
              {!edgeLoading && edgeStories && (
                <ul className="space-y-1.5">
                  {edgeStories.items.slice(0, 4).map((s, j) => (
                    <li key={j} className="flex gap-1.5 text-ui-xs leading-snug text-foreground">
                      <span
                        className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full"
                        style={{ backgroundColor: (DESK[s.desk] ?? NEUTRAL).base }}
                      />
                      <span>
                        {s.headline}
                        <span className="ml-1 text-muted-foreground tabular-nums">· {s.date}</span>
                      </span>
                    </li>
                  ))}
                  {edgeStories.count > 4 && (
                    <li className="text-ui-xs text-muted-foreground">+{edgeStories.count - 4} more</li>
                  )}
                  {edgeStories.count === 0 && (
                    <li className="text-ui-xs italic text-muted-foreground">Recurring co-appearance across desks.</li>
                  )}
                </ul>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-ui-xs text-muted-foreground">
        <LegendDot color={GOLD.base} ring label="Cross-desk — convergence" strong />
        <LegendDot color={DESK.defense.base} label="Defense" />
        <LegendDot color={DESK.ai.base} label="AI Infrastructure" />
        <LegendDot color={DESK.energy.base} label="Energy" />
        <span className="ml-auto italic">Drag to rearrange · hover a node or edge · click a node for its Entity 360</span>
      </div>
    </div>
  );
}

function LegendDot({
  color,
  label,
  ring,
  strong,
}: {
  color: string;
  label: string;
  ring?: boolean;
  strong?: boolean;
}) {
  return (
    <span className={cn("flex items-center gap-1.5", strong && "font-medium text-foreground")}>
      <span
        className="inline-block h-2.5 w-2.5 rounded-full"
        style={{ backgroundColor: color, boxShadow: ring ? `0 0 0 2px #faf9f7, 0 0 6px ${color}` : undefined }}
      />
      {label}
    </span>
  );
}
