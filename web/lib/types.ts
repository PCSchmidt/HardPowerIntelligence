// Response shapes from the FastAPI data boundary (API_SPEC.md). Kept in one place
// so Server Components and helpers share a single contract.

export type Tier = "free" | "pro";
export type Desk = "defense" | "energy" | "ai";
export type ItemType = "award" | "filing" | "policy" | "macro" | "signal";

export interface StalenessIndicator {
  last_updated: string;
  current_status: "pending" | "failed";
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

export interface BriefItem {
  id: string;
  item_type: ItemType;
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
  faithfulness_score: number | null;
  staleness_indicator: StalenessIndicator | null;
  items: BriefItem[];
  citations: Citation[];
  sources_missing: string[];
  model_waterfall: ModelWaterfall;
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
