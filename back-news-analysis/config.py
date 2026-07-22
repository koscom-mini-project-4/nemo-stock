"""back-news-analysis 설정.

OPENAI_API_KEY는 이 디렉터리에 별도로 두지 않고 backend/.env의 값을 그대로 읽는다
(사용자 지시: "openai로 뉴스 분리하는 건 .env에 있는 openai key 사용하면 됩니다").
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_ENV_PATH = ROOT_DIR / "backend" / ".env"
DATA_DIR = Path(__file__).resolve().parent / "data"
NEWS_JSON_PATH = ROOT_DIR / "naver_economy_news.json"

DATA_DIR.mkdir(exist_ok=True)

load_dotenv(BACKEND_ENV_PATH)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
# 채팅(감성/영향도/관련종목) 호출은 백엔드와 동일 모델(gpt-5.6-luna, GPT-5.6 최저가/최속 티어) 사용.
CHAT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.6-luna")
# 클러스터링용 임베딩 모델. 별도 env로 재정의 가능.
EMBEDDING_MODEL = os.environ.get("NEWS_ANALYSIS_EMBEDDING_MODEL", "text-embedding-3-small")

PROMPT_VERSION = "v3"  # impact_strength(3단계) -> impact_grade(예시 앵커 포함 1~9단계) 전환, 캐시 자동 무효화

# 클러스터링: 신규 뉴스 임베딩과 기존 클러스터 대표(centroid) 임베딩의 코사인 유사도가
# 이 값 이상이면 같은 이벤트로 판단, 아니면 새 클러스터 생성.
CLUSTER_SIMILARITY_THRESHOLD = float(os.environ.get("NEWS_ANALYSIS_CLUSTER_THRESHOLD", "0.62"))

JSON_CACHE_PATH = DATA_DIR / "news_ai_cache.json"
SQLITE_CACHE_PATH = DATA_DIR / "news_ai_cache.db"

DEFAULT_POOL_SIZE = 1000
