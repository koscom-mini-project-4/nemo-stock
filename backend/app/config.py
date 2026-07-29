from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(BACKEND_DIR / ".env"), extra="ignore")

    # App
    app_name: str = "nemo-stock"
    debug: bool = True

    # Auth — 이 PoC는 인증 게이트가 없다(§0-17). admin 계정 정보는 시드값(단일 계정)으로만 쓴다.
    admin_username: str = "admin"
    admin_password: str = "admin1234"

    # 포트폴리오(현금) 최초 시드값. 계정에 아직 portfolio_cash 레코드가 없을 때만 사용된다.
    initial_portfolio_cash: float = 10_000_000.0

    # Database
    database_url: str = f"sqlite:///{BACKEND_DIR / 'nemo_stock.db'}"

    # Trigger / worker
    worker_pool_size: int = 4
    scheduler_tick_seconds: float = 1.0
    free_min_interval_sec: int = 60
    pro_min_interval_sec: int = 1

    # Providers
    market_data_provider: str = "dummy"  # dummy | historical | toss | koscom | kis
    order_provider: str = "dummy"  # dummy | toss | kis

    # AI
    ai_provider: str = "openai"  # openai | claude — 어느 쪽을 쓸지 이 값 하나로 결정된다
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.6-luna"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"
    # 전략 생성(AI 초안 생성, POST /ai/generate-draft)만 다른 모델을 쓰고 싶을 때 설정한다
    # (§0-19). 비워두면 openai_model/anthropic_model(AI_PROVIDER에 따라 결정)과 동일한 모델을
    # 그대로 쓴다. 나머지 AI 기능(캔버스 챗봇/백테스트 설명/뉴스 감성/자유 프롬프트)은 항상
    # 기본 모델을 쓴다.
    ai_model_strategy: str | None = None
    ai_prompt_version: str = "v1"

    # 뉴스 기반 매매 판단(newsstock-lib vendored, app/vendor/news_classifier). 자체 SQLite DB를
    # 쓰므로 nemo_stock.db와 별도 파일로 둔다. API 키/모델은 openai_api_key/openai_model 재사용.
    newsstock_db_path: str = str(BACKEND_DIR / "newsstock.db")

    # External public data
    data_go_kr_service_key: str | None = None
    dart_api_key: str | None = None

    # 백테스트 시도 시 종목 데이터가 없으면 네이버 차트 API로 자동 수집(§0-2).
    # 테스트에서는 결정론/오프라인 실행을 위해 명시적으로 false로 오버라이드한다.
    auto_ingest_prices: bool = True

    # Toss (experimental, unverified)
    toss_client_id: str | None = None
    toss_client_secret: str | None = None
    toss_base_url: str = "https://apis.tossinvest.com"
    toss_account_id: str | None = None

    # KOSCOM CHECK-API (실험적/미검증 — CHECK 단말 구독 고객 전용, docs/koscom-api/README.md 참조)
    koscom_cust_id: str | None = None
    koscom_auth_key: str | None = None
    koscom_base_url: str = "https://checkapi.koscom.co.kr"

    # 한국투자증권(KIS) Open API — 공식 예제(github.com/koreainvestment/open-trading-api)
    # 원본 코드 대조로 확인(Toss처럼 순수 추정치가 아님), 실제 앱키로는 미검증.
    # base_url 기본값은 모의투자 서버(openapivts). 실전은 https://openapi.koreainvestment.com:9443.
    kis_app_key: str | None = None
    kis_app_secret: str | None = None
    kis_base_url: str = "https://openapivts.koreainvestment.com:29443"
    kis_is_paper: bool = True
    kis_account_no: str | None = None  # "12345678-01" 형식(계좌번호 8자리-상품코드 2자리)


@lru_cache
def get_settings() -> Settings:
    return Settings()
