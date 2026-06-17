// Pretty display names for raw source_id values (D084). Used by the citations drawer
// and the at-a-glance ledger so provenance reads like a credential, not a slug.
const SOURCE_NAMES: Record<string, string> = {
  edgar: "SEC EDGAR",
  usaspending: "USASpending.gov",
  arxiv: "arXiv",
  gdelt: "GDELT",
  sam_gov: "SAM.gov",
  congress_gov: "Congress.gov",
  fred: "FRED",
  dod_contracts: "DoD Contracts",
};

export function sourceName(sourceId: string): string {
  return SOURCE_NAMES[sourceId] ?? sourceId;
}
