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
    # Cerebras' official recommended replacement after llama-3.3-70b and
    # qwen-3-32b were deprecated (Feb 2026). Marked "high demand" with reduced
    # free-tier limits, so we throttle aggressively below.
    cerebras_model: str = "gpt-oss-120b"
    gemini_model: str = "gemini-2.5-flash"
    gemini_lite_model: str = "gemini-2.5-flash-lite"

    # Inter-call delay (seconds) when Cerebras is the active provider. The
    # nominal free tier is 30 RPM but reduced models (gpt-oss-120b) likely
    # cap lower — 6s/call ≈ 10 RPM, conservatively under any reduced cap.
    cerebras_inter_call_delay: float = 6.0

    # Quota thresholds
    quota_switch_pct: float = 0.90
    max_signals_per_batch: int = 10

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
