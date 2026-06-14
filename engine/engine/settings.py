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
    magnitude_min_window: int = 10
    source_weights: str = (
        '{"usaspending":0.9,"dod_contracts":0.85,"edgar":0.85,'
        '"sam_gov":0.8,"congress_gov":0.8,"fred":0.7,"gdelt":0.5}'
    )
    entity_importance: str = (
        '{"company":1.0,"program":0.85,"person":0.7,'
        '"gov_agency":0.75,"institution":0.6,"sector":0.5,'
        '"security":0.95,"product":0.75,"facility":0.65,'
        '"geography":0.55,"segment":0.7}'
    )

    # Brief generation (D039, D040)
    brief_max_items: int = 8
    brief_min_items: int = 3
    brief_window_hours_fallback: int = 48

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


settings = Settings()
