import { describe, expect, it } from "vitest";
import {
  DEFAULT_PARAMS,
  initialPositions,
  stepSimulation,
  type SimEdge,
  type SimNode,
  type SimParams,
} from "@/lib/graph-layout";

const PARAMS: SimParams = { width: 800, height: 600, ...DEFAULT_PARAMS };

function dist(a: SimNode, b: SimNode) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

describe("initialPositions", () => {
  it("places every id on a circle around the center, deterministically", () => {
    const nodes = initialPositions(["a", "b", "c"], 800, 600);
    expect(nodes.map((n) => n.id)).toEqual(["a", "b", "c"]);
    const r = Math.hypot(nodes[0].x - 400, nodes[0].y - 300);
    for (const n of nodes) {
      expect(Math.hypot(n.x - 400, n.y - 300)).toBeCloseTo(r, 5);
      expect(n.vx).toBe(0);
      expect(n.vy).toBe(0);
    }
    // deterministic: same input → identical output
    expect(initialPositions(["a", "b", "c"], 800, 600)).toEqual(nodes);
  });

  it("handles a single node without dividing by zero", () => {
    const nodes = initialPositions(["solo"], 800, 600);
    expect(Number.isFinite(nodes[0].x)).toBe(true);
    expect(Number.isFinite(nodes[0].y)).toBe(true);
  });
});

describe("stepSimulation", () => {
  it("does not mutate the input nodes (React-safe)", () => {
    const nodes: SimNode[] = [
      { id: "a", x: 100, y: 300, vx: 0, vy: 0 },
      { id: "b", x: 700, y: 300, vx: 0, vy: 0 },
    ];
    const snapshot = structuredClone(nodes);
    stepSimulation(nodes, [], PARAMS);
    expect(nodes).toEqual(snapshot);
  });

  it("pushes two unconnected, close nodes apart (repulsion)", () => {
    const nodes: SimNode[] = [
      { id: "a", x: 395, y: 300, vx: 0, vy: 0 },
      { id: "b", x: 405, y: 300, vx: 0, vy: 0 },
    ];
    const after = stepSimulation(nodes, [], PARAMS);
    expect(dist(after[0], after[1])).toBeGreaterThan(dist(nodes[0], nodes[1]));
  });

  it("pulls two far, connected nodes together (spring)", () => {
    const nodes: SimNode[] = [
      { id: "a", x: 120, y: 300, vx: 0, vy: 0 },
      { id: "b", x: 680, y: 300, vx: 0, vy: 0 },
    ];
    const edges: SimEdge[] = [{ from: "a", to: "b", weight: 2 }];
    const after = stepSimulation(nodes, edges, PARAMS);
    expect(dist(after[0], after[1])).toBeLessThan(dist(nodes[0], nodes[1]));
  });

  it("holds a pinned node fixed while others move", () => {
    const nodes: SimNode[] = [
      { id: "a", x: 395, y: 300, vx: 0, vy: 0 },
      { id: "b", x: 405, y: 300, vx: 0, vy: 0 },
    ];
    const after = stepSimulation(nodes, [], PARAMS, new Set(["a"]));
    expect(after[0].x).toBe(395);
    expect(after[0].y).toBe(300);
    expect(after[1].x).not.toBe(405);
  });

  it("keeps coincident nodes finite (no NaN)", () => {
    const nodes: SimNode[] = [
      { id: "a", x: 400, y: 300, vx: 0, vy: 0 },
      { id: "b", x: 400, y: 300, vx: 0, vy: 0 },
    ];
    const after = stepSimulation(nodes, [], PARAMS);
    for (const n of after) {
      expect(Number.isFinite(n.x)).toBe(true);
      expect(Number.isFinite(n.y)).toBe(true);
    }
    expect(after[0].x).not.toBe(after[1].x);
  });

  it("never lets a node leave the padded bounds", () => {
    let nodes: SimNode[] = [
      { id: "a", x: 30, y: 30, vx: 0, vy: 0 },
      { id: "b", x: 770, y: 570, vx: 0, vy: 0 },
      { id: "c", x: 400, y: 300, vx: 0, vy: 0 },
    ];
    for (let i = 0; i < 200; i++) nodes = stepSimulation(nodes, [], PARAMS);
    for (const n of nodes) {
      expect(n.x).toBeGreaterThanOrEqual(24);
      expect(n.x).toBeLessThanOrEqual(776);
      expect(n.y).toBeGreaterThanOrEqual(24);
      expect(n.y).toBeLessThanOrEqual(576);
    }
  });

  it("settles toward a stable configuration (energy decreases over time)", () => {
    let nodes = initialPositions(["a", "b", "c", "d"], 800, 600);
    const edges: SimEdge[] = [
      { from: "a", to: "b", weight: 1 },
      { from: "b", to: "c", weight: 1 },
      { from: "c", to: "d", weight: 1 },
    ];
    for (let i = 0; i < 400; i++) nodes = stepSimulation(nodes, edges, PARAMS);
    const speed = nodes.reduce((s, n) => s + Math.hypot(n.vx, n.vy), 0);
    expect(speed).toBeLessThan(5); // came to rest
  });
});
