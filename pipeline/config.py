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
    # Switched away from qwen-3-235b-a22b-instruct-2507 — Cerebras free tier has
    # temporarily reduced limits on that hot model, causing 429 on the 2nd call.
    cerebras_model: str = "llama-3.3-70b"
    gemini_model: str = "gemini-2.5-flash"
    gemini_lite_model: str = "gemini-2.5-flash-lite"

    # Inter-call delay (seconds) when Cerebras is the active provider. Free
    # tier nominal limit is 30 RPM; 2.5s/call ≈ 24 RPM → safely under cap.
    cerebras_inter_call_delay: float = 2.5

    # Quota thresholds
    quota_switch_pct: float = 0.90
    max_signals_per_batch: int = 10

    # Pipeline
    scraper_max_concurrent: int = 5
    scraper_delay_range: tuple[float, float] = (1.0, 3.0)

    # Brief settings
    competitor_signals_cap: int = 5
    brief_min_score_customer: int = 2
    brief_min_score_competitor: int = 3

    # Contact discovery
    serper_daily_contact_cap: int = 20
    contact_min_score: int = 3

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
