from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(BACKEND_DIR / ".env"), extra="ignore")

    # App
    app_name: str = "nemo-stock"
    debug: bool = True

    # Auth
    jwt_secret: str = "dev-secret-change-me-please-use-a-long-random-value"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 12
    admin_username: str = "admin"
    admin_password: str = "admin1234"

    # Database
    database_url: str = f"sqlite:///{BACKEND_DIR / 'nemo_stock.db'}"

    # Trigger / worker
    worker_pool_size: int = 4
    scheduler_tick_seconds: float = 1.0
    free_min_interval_sec: int = 60
    pro_min_interval_sec: int = 1

    # Providers
    market_data_provider: str = "dummy"  # dummy | historical | toss
    order_provider: str = "dummy"  # dummy | toss

    # AI
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    ai_prompt_version: str = "v1"

    # External public data
    data_go_kr_service_key: str | None = None
    dart_api_key: str | None = None

    # Toss (experimental, unverified)
    toss_client_id: str | None = None
    toss_client_secret: str | None = None
    toss_base_url: str = "https://apis.tossinvest.com"
    toss_account_id: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
