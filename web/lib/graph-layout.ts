// A small, dependency-free force-directed layout for the convergence graph (§3).
//
// The convergence graph is small (tens of edges, growing slowly), so a full graph library is
// overkill — this is a compact velocity-Verlet-ish simulation: nodes repel (Coulomb), edges pull
// (Hooke), everything drifts toward center, velocity damps each tick. Pure and deterministic (the
// initial layout is a circle, not random) so the physics is unit-testable without a DOM.

export interface SimNode {
  id: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
}

export interface SimEdge {
  from: string;
  to: string;
  weight: number;
}

export interface SimParams {
  width: number;
  height: number;
  repulsion: number; // Coulomb constant — larger spreads nodes apart
  spring: number; // Hooke stiffness on edges
  restLength: number; // ideal edge length
  centering: number; // pull toward the middle (keeps the graph on-screen)
  damping: number; // fraction of velocity retained per tick (0..1)
}

export const DEFAULT_PARAMS: Omit<SimParams, "width" | "height"> = {
  repulsion: 9000,
  spring: 0.03,
  restLength: 140,
  centering: 0.015,
  damping: 0.82,
};

// Deterministic starting layout: evenly spaced on a circle around the center. Deterministic (no
// randomness) so a given graph always settles the same way and tests can assert exact motion.
export function initialPositions(ids: string[], width: number, height: number): SimNode[] {
  const cx = width / 2;
  const cy = height / 2;
  const radius = Math.min(width, height) / 3;
  const n = Math.max(ids.length, 1);
  return ids.map((id, i) => {
    const angle = (2 * Math.PI * i) / n;
    return { id, x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle), vx: 0, vy: 0 };
  });
}

// Advance the simulation one tick, returning NEW node objects (never mutates the input — React-safe).
// `pinned` ids (a node the user is dragging) keep their position and take no forces.
export function stepSimulation(
  nodes: SimNode[],
  edges: SimEdge[],
  params: SimParams,
  pinned: Set<string> = new Set(),
): SimNode[] {
  const { width, height, repulsion, spring, restLength, centering, damping } = params;
  const cx = width / 2;
  const cy = height / 2;
  const fx: Record<string, number> = {};
  const fy: Record<string, number> = {};
  for (const node of nodes) {
    fx[node.id] = 0;
    fy[node.id] = 0;
  }

  // Pairwise repulsion (O(n²) — fine at this scale).
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const a = nodes[i];
      const b = nodes[j];
      let dx = a.x - b.x;
      let dy = a.y - b.y;
      let distSq = dx * dx + dy * dy;
      if (distSq < 0.01) {
        // Coincident nodes: nudge deterministically so the force is finite.
        dx = 0.1 * (i - j);
        dy = 0.1;
        distSq = dx * dx + dy * dy;
      }
      const dist = Math.sqrt(distSq);
      const force = repulsion / distSq;
      const ux = dx / dist;
      const uy = dy / dist;
      fx[a.id] += ux * force;
      fy[a.id] += uy * force;
      fx[b.id] -= ux * force;
      fy[b.id] -= uy * force;
    }
  }

  // Edge springs (heavier edges pull a little harder, capped so one big edge can't collapse the graph).
  const pos = new Map(nodes.map((n) => [n.id, n]));
  for (const edge of edges) {
    const a = pos.get(edge.from);
    const b = pos.get(edge.to);
    if (!a || !b) continue;
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
    const stiffness = spring * Math.min(1 + edge.weight / 4, 2);
    const force = stiffness * (dist - restLength);
    const ux = dx / dist;
    const uy = dy / dist;
    fx[a.id] += ux * force;
    fy[a.id] += uy * force;
    fx[b.id] -= ux * force;
    fy[b.id] -= uy * force;
  }

  return nodes.map((node) => {
    if (pinned.has(node.id)) return { ...node, vx: 0, vy: 0 };
    // Centering pull.
    const cForceX = (cx - node.x) * centering;
    const cForceY = (cy - node.y) * centering;
    let vx = (node.vx + fx[node.id] + cForceX) * damping;
    let vy = (node.vy + fy[node.id] + cForceY) * damping;
    // Terminal-velocity clamp keeps a cold-start blow-up from launching nodes off-screen.
    const speed = Math.sqrt(vx * vx + vy * vy);
    const maxSpeed = 40;
    if (speed > maxSpeed) {
      vx = (vx / speed) * maxSpeed;
      vy = (vy / speed) * maxSpeed;
    }
    const margin = 24;
    const x = Math.max(margin, Math.min(width - margin, node.x + vx));
    const y = Math.max(margin, Math.min(height - margin, node.y + vy));
    return { ...node, x, y, vx, vy };
  });
}
