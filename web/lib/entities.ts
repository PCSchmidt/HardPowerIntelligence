// Entity display helpers (T3.5/T3.6, D091).

// Desk display labels (no central map elsewhere; navbar has inline copy).
export const DESK_LABEL: Record<string, string> = {
  defense: "Defense",
  ai: "AI Infrastructure",
  energy: "Energy",
};

export function deskLabel(desk: string): string {
  return DESK_LABEL[desk] ?? desk;
}

// Authoritative identifier labels for the Entity 360 view.
export const ID_TYPE_LABEL: Record<string, string> = {
  ticker: "Ticker",
  cik: "SEC CIK",
  uei: "SAM UEI",
  lei: "LEI",
  figi: "FIGI",
  duns: "DUNS",
};


// SEC `company_tickers.json` titles are inconsistently cased — some all-caps ("CENTRUS ENERGY
// CORP"), some already mixed ("D-Wave Quantum Inc."). Title-case only the all-caps ones so chips
// read cleanly without mangling a name that already has intentional casing.
export function entityDisplayName(name: string): string {
  const hasLowercase = /[a-z]/.test(name);
  if (hasLowercase) return name;
  return name
    .toLowerCase()
    .replace(/\b([a-z])/g, (_, c: string) => c.toUpperCase());
}
