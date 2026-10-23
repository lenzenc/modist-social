from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    database_url: str = "postgresql+asyncpg://modist:modist@localhost:5433/modist"

    anthropic_api_key: str = ""
    model: str = "claude-haiku-5-5"
    # "live" calls Anthropic; "mock" uses canned lines so the whole sim runs for $0.
    llm_mode: str = "live"
    max_concurrent_llm: int = 3
    max_output_tokens: int = 300

    daily_budget_usd: float = 2.00
    web_search_enabled: bool = True
    max_lookups_per_sim_hour: int = 6
    brewery_city: str = "Minneapolis, MN"

    # New people who walk in and are generated on the fly. The cap counts every patron, seeded or new.
    newcomers_enabled: bool = True
    newcomers_per_week: float = 8.0
    max_patrons: int = 150
    # Parties (2-8 people) who walk in together: regulars, regulars with new people, or all new faces.
    groups_enabled: bool = True
    groups_per_week: float = 30.0

    # Tell speakers which phrases and openers the room has worn out (see sim/realism.py). Costs a few input tokens a turn.
    realism_feedback: bool = True

    # One small batched call writes fresh idle beats (a glance at the phone, a fidget) for the room; code templates fill in otherwise.
    llm_beats: bool = True
    beat_calls_per_sim_hour: int = 1

    # Sim minutes that pass per real minute.
    sim_speed: float = 15.0

    # Haiku 5.5 list prices, USD per million tokens (prompts up to 100K).
    price_input: float = 0.10
    price_output: float = 0.50
    price_cache_read: float = 0.01
    price_cache_write: float = 0.125
    price_web_search: float = 0.01  # per search


settings = Settings()
