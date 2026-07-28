"""뉴스 기반 매매 판단 라이브러리.

    from news_classifier import NewsTrader
    trader = NewsTrader()
    trader.decide(stock="삼성전자", sector="반도체 및 반도체 장비", macro="증권")

계층
    crawler   네이버 경제뉴스 증분 수집 (해시로 중복 관리)
    pipeline  수집한 뉴스를 AI 로 분류 -> 클러스터 -> A/B/C 테이블
    indicator A/B/C 각 지표 계산 (점수식 + t/n/f)
    decision  A/B/C 를 합쳐 매매 판단
    api       위를 하나로 묶은 NewsTrader 파사드
"""
from . import crawler, db, decision, indicator, pipeline
from .api import NewsTrader
from .config import SECTORS, MACROS, STRENGTHS, Settings
from .indicator import macro_indicator, sector_indicator, stock_indicator
from .pipeline import classify_many, classify_news

__all__ = [
    "NewsTrader", "Settings",
    "crawler", "db", "decision", "indicator", "pipeline",
    "classify_news", "classify_many",
    "stock_indicator", "sector_indicator", "macro_indicator",
    "SECTORS", "MACROS", "STRENGTHS",
]
