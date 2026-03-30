"""Centralized configuration with Pydantic validation."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM providers (empty string = not configured, validated at call time)
    groq_api_key: str = ""
    cerebras_api_key: str = ""
    gemini_api_key: str = ""

    # Database
    neon_database_url: str = ""

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Optional (Phase 2)
    serper_api_key: str = ""
    resend_api_key: str = ""

    # LLM config
    groq_model: str = "llama-3.3-70b-versatile"
    cerebras_model: str = "qwen-3-235b-a22b-instruct-2507"
    gemini_model: str = "gemini-2.5-flash"
    gemini_lite_model: str = "gemini-2.5-flash-lite"

    # Quota thresholds
    groq_quota_switch_pct: float = 0.80
    max_signals_per_batch: int = 5
    max_retries_per_provider: int = 2

    # Pipeline
    scraper_max_concurrent: int = 5
    scraper_delay_range: tuple[float, float] = (1.0, 3.0)

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
