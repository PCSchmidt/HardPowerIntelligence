from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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

    # Materiality scoring (D030)
    materiality_threshold: float = 0.35

    # RAG retrieval (D031)
    rag_passage_top_k: int = 20
    rag_graph_edge_limit: int = 50

    # Data source API keys
    sam_gov_api_key: str = ""
    edgar_user_agent: str = "HardPowerIntelligence/1.0 hardpowerintelligence@gmail.com"

    # Worker
    worker_concurrency: int = 5


settings = Settings()
