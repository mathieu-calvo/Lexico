"""Application configuration via environment variables and .env file."""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Lexico settings.

    All settings can be overridden via environment variables with the LEXICO_
    prefix, or via a .env file in the project root.
    """

    # Providers (dictionary first, then LLM chain).
    # Paid providers (claude) are intentionally NOT in the default chain —
    # Lexico runs at $0/month by default. Opt in by adding "claude" to the
    # chain AND raising daily_usd_cap above 0.
    provider_order: str = "stub,wiktionary,groq"
    groq_api_key: str | None = None
    anthropic_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    claude_lookup_model: str = "claude-haiku-4-5"
    claude_tutor_model: str = "claude-sonnet-4-6"
    prompt_version: str = "2026-04-13"

    # Cache / storage
    cache_dir: Path = Path.home() / ".lexico"
    memory_cache_ttl_hours: int = 24

    # Cost guardrails. The USD cap defaults to 0.00 so no paid provider can
    # ever spend money without an explicit opt-in by raising this value.
    max_llm_calls_per_user_per_day: int = 50
    max_llm_calls_per_day: int = 500
    daily_usd_cap: float = 0.00

    # Cloud / auth
    database_url: str | None = None
    require_auth: bool = False

    # UI
    default_source_lang: str = "fr"

    model_config = {
        "env_prefix": "LEXICO_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }

    @property
    def db_path(self) -> Path:
        return self.cache_dir / "lexico.db"

    @property
    def kaikki_dir(self) -> Path:
        return self.cache_dir / "kaikki"

    @property
    def provider_chain(self) -> list[str]:
        return [p.strip() for p in self.provider_order.split(",") if p.strip()]


def _load_settings() -> Settings:
    """Load settings, supplementing with Streamlit secrets when available."""
    s = Settings()
    try:
        import streamlit as st  # type: ignore

        if "GROQ_API_KEY" in st.secrets and not s.groq_api_key:
            s.groq_api_key = st.secrets["GROQ_API_KEY"]
        if "ANTHROPIC_API_KEY" in st.secrets and not s.anthropic_api_key:
            s.anthropic_api_key = st.secrets["ANTHROPIC_API_KEY"]
        if "database" in st.secrets and not s.database_url:
            s.database_url = st.secrets["database"].get("url") or None
        if not s.require_auth and "credentials" in st.secrets:
            s.require_auth = True
    except Exception:
        pass
    return s


settings = _load_settings()
