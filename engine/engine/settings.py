from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root: engine/engine/settings.py → parents[2]. Loading by absolute path makes
# config independent of the process working directory (e.g. `cd api && uvicorn`).
_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_REPO_ROOT / ".env", extra="ignore")

    # Supabase
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""
    database_url: str = ""

    # OpenRouter
    openrouter_api_key: str = ""
    llm_model_extraction: str = "openrouter/deepseek/deepseek-v4-flash"
    llm_model_disambiguation: str = "openrouter/deepseek/deepseek-v4-flash"
    llm_model_synthesis: str = "openrouter/deepseek/deepseek-v4-pro"
    llm_model_eval: str = "openrouter/qwen/qwen3.7-max"
    llm_model_synthesis_fallback: str = "openrouter/qwen/qwen3.7-max"
    llm_model_fallback_last_resort: str = "claude-sonnet-4-6"

    # LLM transient-failure resilience (D076). The daily run fires several calls per
    # desk across three desks back-to-back; the OpenRouter free tier rate-limits (429)
    # under that burst, and a 429 is a *time window* — the brief-level re-roll (D072)
    # retries immediately and lands inside the same blocked window, so it can't clear
    # it. These add delay-and-retry with exponential backoff + jitter at the call layer
    # so a transient 429 / 5xx / connection blip self-heals before it fails a desk.
    llm_max_retries: int = 4               # retries after the first try (5 attempts total)
    llm_backoff_base_seconds: float = 2.0  # first backoff; doubles each retry
    llm_backoff_max_seconds: float = 30.0  # cap per-retry sleep

    # Anthropic
    anthropic_api_key: str = ""

    # Budget guards
    llm_daily_budget_usd: float = 5.0
    llm_monthly_budget_usd: float = 50.0

    # OpenAI (embeddings)
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # Entity resolution thresholds (D027)
    entity_resolution_high_threshold: float = 0.92
    entity_resolution_medium_threshold: float = 0.70
    entity_resolution_low_threshold: float = 0.55

    # Eval gate (D016)
    brief_faithfulness_threshold: float = 0.95

    # LLM determinism (D058): synthesis + eval run at temperature 0 so brief
    # generation is reproducible and stays faithful to terse source records.
    llm_temperature: float = 0.0

    # Materiality scoring (D030, D035, D036)
    materiality_threshold: float = 0.35
    # Cross-sector convergence boost (D060): multiply a record's score by
    # (1 + weight·(desks−1), capped at +2 desks). Rewards items touching ≥2 desks.
    materiality_cross_sector_weight: float = 0.15
    magnitude_min_window: int = 10
    source_weights: str = (
        '{"usaspending":0.9,"dod_contracts":0.85,"edgar":0.85,'
        '"sam_gov":0.8,"congress_gov":0.8,"arxiv":0.7,"fred":0.7,"gdelt":0.5}'
    )
    entity_importance: str = (
        '{"company":1.0,"program":0.85,"person":0.7,'
        '"gov_agency":0.75,"institution":0.6,"sector":0.5,'
        '"security":0.95,"product":0.75,"facility":0.65,'
        '"geography":0.55,"segment":0.7}'
    )

    # Novelty / anti-rehash (D074): down-rank a record whose (source_id, native_id) was
    # already cited in a PUBLISHED brief for this desk within the last
    # ``novelty_window_days`` by multiplying its materiality score by ``novelty_penalty``.
    # Demotes (doesn't drop) so a long-lived item only re-leads when nothing fresher
    # exists. penalty 1.0 disables; window 0 disables.
    novelty_window_days: int = 7
    novelty_penalty: float = 0.5

    # Brief generation (D039, D040)
    brief_max_items: int = 8
    brief_min_items: int = 3
    brief_window_hours_fallback: int = 48
    # Multi-source briefs (D068): reserve up to N fact slots for advancement
    # (research_paper) records so high-$ capital doesn't crowd out the technology
    # leg of a brief (D063). 0 disables the floor.
    brief_advancement_floor: int = 3
    # Publish gate (D070): a brief publishes when it has >= this many provable
    # (LLM-supported) claims. Counts claims, not items, so it's stable whether
    # synthesis consolidates facts into few dense items or many thin ones.
    brief_min_claims: int = 3
    # Regenerate-on-failure (D072): the synthesis model is non-deterministic, so a
    # gate failure is often a bad draw a re-run clears. Regenerate up to this many
    # times before persisting the best attempt as failed. 1 disables retries.
    brief_max_attempts: int = 3
    # Analysis grounding gate (D073): when eval_analysis flags an analysis field as
    # fabricating a specific, rewrite it this many times before omitting it. 0 omits
    # immediately (no regeneration).
    analysis_max_regen: int = 1

    # RAG retrieval (D031)
    rag_passage_top_k: int = 20
    rag_graph_edge_limit: int = 50

    # Data source API keys
    sam_gov_api_key: str = ""
    edgar_user_agent: str = "HardPowerIntelligence/1.0 hardpowerintelligence@gmail.com"

    # Worker
    worker_concurrency: int = 5

    # Ingestion runner (D004, D055)
    ingest_max_pages: int = 10          # safety cap on pagination per run
    ingest_hot_window_days: int = 21    # retention window for normalized + raw records

    # EDGAR filing-body extraction (D078). Fetch each hit's actual document and mine it
    # for dollar amounts / dates / percentages so the publish gate has checkable facts.
    edgar_fetch_bodies: bool = True
    edgar_max_bodies_per_run: int = 80  # cap body fetches (cost/time + SEC courtesy)
    edgar_body_excerpt_chars: int = 1200  # body excerpt folded into the embedded chunk


settings = Settings()
