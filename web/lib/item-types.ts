import { Award, FileText, Landmark, LineChart, Radio, type LucideIcon } from "lucide-react";
import type { ItemType } from "./types";

// Single source of truth for per-item-type presentation (D087). Label, color token, and
// icon were duplicated across brief-glance + brief-content; centralizing keeps the
// at-a-glance ledger and the long read visually consistent and adds the type icon layer.

export const ITEM_LABEL: Record<ItemType, string> = {
  award: "Award",
  filing: "Filing",
  policy: "Policy",
  macro: "Macro",
  signal: "Signal",
};

// Background fills (magnitude bars, swatches).
export const ITEM_BG: Record<ItemType, string> = {
  award: "bg-item-award",
  filing: "bg-item-filing",
  policy: "bg-item-policy",
  macro: "bg-item-macro",
  signal: "bg-item-signal",
};

// Foreground tint (the type icon).
export const ITEM_TEXT: Record<ItemType, string> = {
  award: "text-item-award",
  filing: "text-item-filing",
  policy: "text-item-policy",
  macro: "text-item-macro",
  signal: "text-item-signal",
};

// Consistent glyph per type — an award (contract), a document (filing), a government
// building (policy), a trend line (macro), a broadcast (signal).
export const ITEM_ICON: Record<ItemType, LucideIcon> = {
  award: Award,
  filing: FileText,
  policy: Landmark,
  macro: LineChart,
  signal: Radio,
};
