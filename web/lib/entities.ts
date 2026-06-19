// Entity display helpers (T3.5, D091).

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
