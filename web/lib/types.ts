// Response shapes from the FastAPI data boundary (API_SPEC.md). Kept in one place
// so Server Components and helpers share a single contract.

export type Tier = "free" | "pro";
export type Desk = "defense" | "energy" | "ai";
export type ItemType = "award" | "filing" | "policy" | "macro" | "signal";

export interface StalenessIndicator {
  last_updated: string | null;
  // pending/failed = D013 generation issue (alarming, amber). latest_available = a quiet day or
  // pre-cron load where the served brief simply isn't today's (neutral, informational).
  current_status: "pending" | "failed" | "latest_available";
  message: string;
}

export interface Citation {
  id: string;
  source_id: string;
  url: string;
  fetched_at: string;
  native_id: string;
  license_class: string;
  title: string | null;
  excerpt: string | null;
}

// Epistemic confidence/attribution tier (D098/D099): the basis on which an item's
// facts are evidenced, shown to the reader as estimative framing.
export type Attribution = "confirmed" | "reported" | "analysis" | "speculative";

export interface BriefItem {
  id: string;
  item_type: ItemType;
  // Confidence/attribution label (D099). Defaults to "confirmed" for pre-D099 items.
  attribution: Attribution;
  headline: string;
  body: string;
  // Analysis layer (D071/D073): grounded HPI interpretation. Empty string when the
  // grounding gate withheld it — render nothing, never a placeholder.
  read: string;
  watch: string;
  entity_ids: string[];
  citation_ids: string[];
  materiality_score: number | null;
  display_order: number;
}

// Resolved entity chip summary (T3.4, D091). is_private = no current ticker (a closely-held /
// venture firm minted from a CIK/UEI during resolution, D092) — rendered as a name-only chip.
export interface EntitySummary {
  id: string;
  name: string;
  type: string;
  ticker: string | null;
  is_private: boolean;
  // True when the entity has appeared on ≥2 desks — the cross-desk convergence signal (T3.7).
  convergence: boolean;
}

// Entity 360 payload from GET /entities/{id} (T3.6, D091).
export interface EntityAppearance {
  brief_id: string;
  desk: string;
  date: string;
  headline: string;
  item_type: ItemType;
}

export interface EntityDetail {
  id: string;
  name: string;
  type: string;
  ticker: string | null;
  is_private: boolean;
  identifiers: { type: string; value: string }[];
  // Distinct desks the entity appears on; convergence = spans ≥2 desks (T3.7).
  desks: string[];
  convergence: boolean;
  appearances: EntityAppearance[];
}

// GDELT lead-theme volume series for the Signal sparkline (D089).
export interface SignalSeries {
  theme: string;
  series: number[];
  delta_pct: number | null;
  direction: "up" | "down" | null;
}

export interface ModelWaterfall {
  synthesis_model: string | null;
  eval_model: string | null;
  eval_passed: boolean | null;
}

export interface Brief {
  id: string;
  desk: Desk;
  date: string;
  status: "pending" | "published" | "failed";
  published_at: string | null;
  headline: string | null;
  bluf: string | null;
  // Cross-signal thesis tying the day's items together (D071/D073). "" if none.
  convergence_read: string;
  // GDELT media-attention momentum (D082): labeled aggregate color, not a cited fact. "" if none.
  signal?: string;
  // Lead-theme volume series for the Signal sparkline (D089); null/absent if none.
  signal_series?: SignalSeries | null;
  faithfulness_score: number | null;
  staleness_indicator: StalenessIndicator | null;
  // Resolved entities referenced by the items (T3.4, D091); reader maps item.entity_ids → these.
  entities: EntitySummary[];
  items: BriefItem[];
  citations: Citation[];
  sources_missing: string[];
  model_waterfall: ModelWaterfall;
}

// "Full Wire" overflow (D112): material, on-thesis items that cleared scoring but lost the
// brief's space cut. Listed with no narrative — title + source + link — so nothing relevant
// is thrown away on a heavy news day.
export interface WireItem {
  source_id: string;
  native_id: string | null;
  item_type: string | null;
  headline: string;
  url: string | null;
  materiality_score: number | null;
}

export interface Wire {
  desk: Desk;
  brief_id: string;
  date: string;
  published_at: string | null;
  items: WireItem[];
}

export interface AuthMe {
  user_id: string;
  email: string;
  tier: Tier;
  subscribed_at: string | null;
  current_period_end: string | null;
  source?: "lemonsqueezy" | "comp" | null;
  customer_portal_url?: string | null;
}

export interface CalendarEvent {
  id: string;
  event_type: string;
  title: string;
  event_date: string;
  event_time_utc: string | null;
  desk: string[];
  entity_ids: string[];
  source_url: string | null;
}

export interface ApiError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface ApiResult<T> {
  data: T | null;
  status: number;
  error?: ApiError;
}
