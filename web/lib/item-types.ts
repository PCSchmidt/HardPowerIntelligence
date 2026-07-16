import {
  Award,
  FileText,
  FlaskConical,
  Landmark,
  LineChart,
  Radar,
  Radio,
  type LucideIcon,
} from "lucide-react";
import type { ItemType } from "./types";

// Single source of truth for per-item-type presentation (D087). Label, color token, and
// icon were duplicated across brief-glance + brief-content; centralizing keeps the
// at-a-glance ledger and the long read visually consistent and adds the type icon layer.
// "operational" + "research" added D143 — every map here MUST cover every ItemType, or an
// unmapped value renders `undefined` and crashes the desk page (the D140 failure, one layer up).

export const ITEM_LABEL: Record<ItemType, string> = {
  award: "Award",
  filing: "Filing",
  policy: "Policy",
  macro: "Macro",
  signal: "Signal",
  operational: "Operational",
  research: "Research",
};

// Background fills (magnitude bars, swatches).
export const ITEM_BG: Record<ItemType, string> = {
  award: "bg-item-award",
  filing: "bg-item-filing",
  policy: "bg-item-policy",
  macro: "bg-item-macro",
  signal: "bg-item-signal",
  operational: "bg-item-operational",
  research: "bg-item-research",
};

// Foreground tint (the type icon).
export const ITEM_TEXT: Record<ItemType, string> = {
  award: "text-item-award",
  filing: "text-item-filing",
  policy: "text-item-policy",
  macro: "text-item-macro",
  signal: "text-item-signal",
  operational: "text-item-operational",
  research: "text-item-research",
};

// Consistent glyph per type — an award (contract), a document (filing), a government
// building (policy), a trend line (macro), a broadcast (signal), a radar sweep (operational
// — a real-world action/deployment), a lab flask (research — an R&D/tech milestone).
export const ITEM_ICON: Record<ItemType, LucideIcon> = {
  award: Award,
  filing: FileText,
  policy: Landmark,
  macro: LineChart,
  signal: Radio,
  operational: Radar,
  research: FlaskConical,
};
