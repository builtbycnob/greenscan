"""Centralized configuration with Pydantic validation."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM providers (empty string = not configured, validated at call time)
    groq_api_key: str = ""
    cerebras_api_key: str = ""
    gemini_api_key: str = ""

    # Database
    neon_database_url: str = ""

    # Telegram (comma-separated chat IDs for multi-recipient delivery)
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    @property
    def telegram_chat_ids(self) -> list[str]:
        """Parse comma-separated chat IDs into a list."""
        if not self.telegram_chat_id:
            return []
        return [cid.strip() for cid in self.telegram_chat_id.split(",") if cid.strip()]

    # Optional (Phase 2)
    serper_api_key: str = ""
    resend_api_key: str = ""

    # LLM config
    groq_model: str = "llama-3.3-70b-versatile"
    # Live probe 2026-06-01: this account's free tier lists ONLY gpt-oss-120b
    # (production) + zai-glm-4.7 (preview); both POST 200. qwen-3-235b returns
    # 404 "no access" — delisted from the free roster (Dedicated/paid only).
    cerebras_model: str = "gpt-oss-120b"
    gemini_model: str = "gemini-2.5-flash"
    gemini_lite_model: str = "gemini-2.5-flash-lite"

    # OpenRouter (funded $10 once → 1000 RPD / 20 RPM). OpenAI-compatible.
    openrouter_api_key: str = ""
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct:free"
    openrouter_inter_call_delay: float = 3.0  # ≤20 RPM

    # Mistral (free, no card; 1B tok/month; 2 RPM). OpenAI-compatible.
    mistral_api_key: str = ""
    mistral_model: str = "mistral-small-latest"
    mistral_inter_call_delay: float = 31.0  # ≤2 RPM

    # Cerebras free tier = 5 RPM per model → 1 call / 12s (old 6.0 ≈ 10 RPM
    # exceeded the cap and tripped burst-429s).
    cerebras_inter_call_delay: float = 12.0

    # Quota thresholds
    quota_switch_pct: float = 0.90
    max_signals_per_batch: int = 15

    # Transient-throttle retry budget (per provider, per call) before switching.
    throttle_retry_max_attempts: int = 4

    # Pipeline
    scraper_max_concurrent: int = 5
    scraper_delay_range: tuple[float, float] = (1.0, 3.0)

    # Brief settings
    competitor_signals_cap: int = 5
    # Raised from 2/3 → 3/4 because lower thresholds let the brief balloon to
    # 5 Telegram chunks (~20K chars), causing the last chunks (incl. People to
    # Watch) to be dropped on send.
    brief_min_score_customer: int = 3
    brief_min_score_competitor: int = 4
    # Hard cap on signals included in the brief, regardless of threshold.
    # Top-N by score; ties broken by competitor-first (already cap'd separately).
    brief_max_total_signals: int = 15

    # Contact discovery
    serper_daily_contact_cap: int = 20
    contact_min_score: int = 3

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
