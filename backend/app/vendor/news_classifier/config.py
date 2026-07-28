"""설정값. .env 에서 읽는다."""
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

_db = os.getenv("DB_PATH", "news.db")
DB_PATH = _db if os.path.isabs(_db) else str(BASE_DIR / _db)

CLUSTER_RETENTION_DAYS = int(os.getenv("CLUSTER_RETENTION_DAYS", "7"))
CONTENT_MAX_CHARS = int(os.getenv("CONTENT_MAX_CHARS", "1500"))

# ---------------------------------------------------------------- 크롤러
NAVER_LIST_URL = "https://news.naver.com/main/list.naver?mode=LSD&mid=sec&sid1=101"
CRAWL_DAYS = int(os.getenv("CRAWL_DAYS", "1"))
CRAWL_MAX_PAGES = int(os.getenv("CRAWL_MAX_PAGES", "5"))
CRAWL_DELAY = (1.2, 2.2)          # 기사 사이 랜덤 대기 (초)
CRAWL_TIMEOUT = 10
CRAWLED_RETENTION_DAYS = int(os.getenv("CRAWLED_RETENTION_DAYS", "90"))

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
HTTP_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
    "Referer": "https://news.naver.com/",
}

# 분류 허용값 (이 밖의 값은 전부 null 처리)
# GICS 산업그룹 24개
SECTORS = [
    "에너지",
    "소재",
    "자본재",
    "상업 및 전문 서비스",
    "운송",
    "자동차 및 부품",
    "내구소비재 및 의류",
    "소비자 서비스",
    "자유소비재 유통 및 소매",
    "필수소비재 유통 및 소매",
    "식품·음료 및 담배",
    "가정 및 개인용품",
    "헬스케어 장비 및 서비스",
    "제약·생명공학 및 생명과학",
    "은행",
    "금융 서비스",
    "보험",
    "소프트웨어 및 서비스",
    "기술 하드웨어 및 장비",
    "반도체 및 반도체 장비",
    "전기통신 서비스",
    "미디어 및 엔터테인먼트",
    "유틸리티",
    "부동산",
]

MACROS = [
    "금융", "증권", "산업/재계", "중기/벤처", "부동산",
    "글로벌 경제", "생활경제", "경제 일반",
]

STRENGTHS = [-1.0, -0.6, -0.3, 0.0, 0.3, 0.6, 1.0]

DATE_FMT = "%Y-%m-%d %H:%M:%S"


@dataclass
class Settings:
    """NewsTrader 인스턴스 하나의 동작을 결정하는 값들.

    전부 기본값이 있으므로 `Settings()` 만으로도 동작한다.
    바꾸고 싶은 것만 키워드로 넘기면 된다.
    """

    # --- 저장소 / 모델 -------------------------------------------------
    db_path: str = DB_PATH
    model: str = OPENAI_MODEL
    api_key: str = OPENAI_API_KEY
    content_max_chars: int = CONTENT_MAX_CHARS

    # --- 자동 업데이트 -------------------------------------------------
    auto_update: bool = True            # 조회할 때 스스로 크롤링+분류할지
    update_interval_min: int = 30       # 마지막 갱신 후 이 시간이 지나야 다시 돈다
    crawl_days: int = CRAWL_DAYS        # 며칠치 목록을 훑을지
    crawl_max_pages: int = CRAWL_MAX_PAGES
    max_classify_per_update: int = 100  # 한 번 갱신에 분류할 최대 뉴스 수 (API 비용 상한)

    # --- 보관 ----------------------------------------------------------
    retention_days: int = CLUSTER_RETENTION_DAYS
    crawled_retention_days: int = CRAWLED_RETENTION_DAYS

    # --- 지표 계산 -----------------------------------------------------
    period_days: int = 7                # 기본 조회 기간
    threshold: float = 0.1              # t / f 경계
    decay_base: float = 0.3             # 계산식의 0.3
    include_zero: bool = True           # strength=0 클러스터를 분모에 포함할지
    decay_from: str = "end"             # d 기준: "end" | "start" | "now"

    # --- 매매 판단 (A/B/C 종합) ----------------------------------------
    weights: dict = field(default_factory=lambda: {"A": 0.5, "B": 0.3, "C": 0.2})
    combine: str = "weighted"           # "weighted" | "vote" | "stock_first"
    signal_style: str = "tfn"           # "tfn" | "trade" | "score"

    def __post_init__(self):
        if self.decay_from not in ("end", "start", "now"):
            raise ValueError(f"decay_from 은 end/start/now 중 하나: {self.decay_from!r}")
        if self.combine not in ("weighted", "vote", "stock_first"):
            raise ValueError(f"combine 은 weighted/vote/stock_first 중 하나: {self.combine!r}")
        if self.signal_style not in ("tfn", "trade", "score"):
            raise ValueError(f"signal_style 은 tfn/trade/score 중 하나: {self.signal_style!r}")
