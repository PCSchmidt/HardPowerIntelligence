import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

// Strip [CITE:N] markers from text rendered as plain prose (e.g. the BLUF). Item
// bodies render these as clickable chips via CitedBody, but the BLUF/summary is a
// plain paragraph — the synthesis occasionally emits citation markers there, which
// would otherwise leak as literal "[CITE:1]" text. Removes the marker plus any
// leading whitespace so "LLC [CITE:1]." → "LLC.".
export function stripCiteMarkers(text: string): string {
  return text.replace(/\s*\[CITE:\d+\]/g, "").trim()
}
