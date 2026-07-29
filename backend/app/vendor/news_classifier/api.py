"""라이브러리 진입점.

    from news_classifier import NewsTrader

    trader = NewsTrader()                        # 기본 설정
    print(trader.stock("삼성전자"))               # A 지표
    print(trader.decide(stock="삼성전자",
                        sector="반도체 및 반도체 장비",
                        macro="증권"))            # 매매 판단

조회 메서드를 부르면 인스턴스가 알아서
  1) 마지막 갱신 후 update_interval_min 이 지났으면 네이버에서 새 기사만 크롤링하고
  2) 아직 분류 안 된 기사를 AI 에 넣어 클러스터/A·B·C 테이블에 반영하고
  3) 보관기간 지난 클러스터를 정리한 뒤
  4) 지표를 계산해서 돌려준다.

자동 갱신을 끄려면 `NewsTrader(auto_update=False)` 로 만들고 `update()` 를 직접 부른다.
"""
from datetime import datetime

from . import crawler, db, decision, indicator
from .config import DATE_FMT, Settings
from .db import GROUPS
from .pipeline import classify_many


class NewsTrader:
    """뉴스 기반 매매 판단 라이브러리.

    파라미터는 전부 Settings 의 필드다. 바꾸고 싶은 것만 키워드로 넘기면 된다.

        NewsTrader(auto_update=False, period_days=14, include_zero=False,
                   signal_style="trade", weights={"A": 0.6, "B": 0.3, "C": 0.1})
    """

    def __init__(self, settings: Settings = None, **overrides):
        if settings is not None and overrides:
            raise TypeError("settings 와 개별 옵션은 같이 못 쓴다. 둘 중 하나만.")
        self.settings = settings or Settings(**overrides)
        self._conn = None

    # ------------------------------------------------------------ 연결
    @property
    def conn(self):
        if self._conn is None:
            self._conn = db.connect(self.settings.db_path)
        return self._conn

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ------------------------------------------------------------ 갱신
    def update(self, force: bool = False, progress=None,
               days: int = None, keywords: list = None, max_pages: int = None) -> dict:
        """크롤링 -> 분류 -> 정리. 실제로 한 일을 요약해서 돌려준다.

        force=False 면 마지막 갱신 후 update_interval_min 이 안 지났을 때 건너뛴다.
        days/keywords/max_pages(§0-12/nemo-stock 후속): 주어지면 이번 호출 1회만 Settings
        기본값을 오버라이드한다(전역 설정은 그대로 — 1회성 트리거용, 예: "최근 N일치만,
        특정 키워드만, 날짜당 최대 페이지 수를 늘려서").
        """
        s = self.settings
        since = crawler.minutes_since_last_crawl(self.conn)
        if not force and since < s.update_interval_min:
            return {"건너뜀": True, "마지막갱신후_분": round(since, 1),
                    "수집": 0, "분류": 0, "삭제클러스터": 0}

        crawled = crawler.crawl(
            self.conn,
            days=days if days is not None else s.crawl_days,
            max_pages=max_pages if max_pages is not None else s.crawl_max_pages,
            workers=s.crawl_workers, progress=progress,
            keywords=keywords if keywords is not None else s.crawl_keywords,
        )

        pending = db.pending_news(self.conn, limit=s.max_classify_per_update)
        classified = []
        if pending:
            classify_many(self.conn, pending, purge=False,
                          progress=(lambda i, n: progress(i, f"분류 {i}/{n}"))
                          if progress else None,
                          model=s.model, api_key=s.api_key)
            classified = [n["url_hash"] for n in pending]
            db.mark_classified(self.conn, classified)

        now = db.latest_timestamp(self.conn, datetime.now().strftime(DATE_FMT))
        purged = db.purge_old_clusters(self.conn, now, s.retention_days)
        db.purge_crawled(self.conn, s.crawled_retention_days)

        return {"건너뜀": False, "수집": len(crawled), "분류": len(classified),
                "미분류잔여": len(db.pending_news(self.conn)),
                "삭제클러스터": purged}

    def _auto(self):
        if self.settings.auto_update:
            self.update()

    # ------------------------------------------------------------ 지표
    def _indicator(self, group: str, key: str, start, period) -> dict:
        s = self.settings
        self._auto()
        return indicator.compute(
            self.conn, group, key,
            start or datetime.now().strftime("%Y-%m-%d"),
            period or s.period_days,
            threshold=s.threshold, decay_base=s.decay_base,
            include_zero=s.include_zero, decay_from=s.decay_from,
        )

    def stock(self, name: str, start: str = None, period: int = None) -> dict:
        """A — 종목 영향 지표"""
        return self._indicator("A", name, start, period)

    def sector(self, name: str, start: str = None, period: int = None) -> dict:
        """B — 섹터 영향 지표"""
        return self._indicator("B", name, start, period)

    def macro(self, name: str, start: str = None, period: int = None) -> dict:
        """C — 거시 영향 지표"""
        return self._indicator("C", name, start, period)

    def rank(self, group: str, start: str = None, period: int = None,
             limit: int = None) -> list:
        """그룹 안의 모든 키를 평균 내림차순으로. 오늘 뭐가 좋고 나쁜지 훑을 때."""
        s = self.settings
        self._auto()
        start = start or datetime.now().strftime("%Y-%m-%d")
        period = period or s.period_days
        w_start, w_end = indicator.window(start, period)
        keys = db.group_keys(self.conn, group.upper(), w_start, w_end)
        out = [indicator.compute(
            self.conn, group, k, start, period,
            threshold=s.threshold, decay_base=s.decay_base,
            include_zero=s.include_zero, decay_from=s.decay_from) for k in keys]
        out.sort(key=lambda r: r["평균"], reverse=True)
        return out[:limit] if limit else out

    # ------------------------------------------------------------ 매매 판단
    def decide(self, stock: str = None, sector: str = None, macro: str = None,
               start: str = None, period: int = None, detail: bool = True) -> dict:
        """A/B/C 를 합쳐 하나의 매매 판단으로. 준 키만 계산한다."""
        if not (stock or sector or macro):
            raise ValueError("stock / sector / macro 중 최소 하나는 필요하다.")
        s = self.settings
        self._auto()
        return decision.decide(
            self.conn, start or datetime.now().strftime("%Y-%m-%d"),
            period or s.period_days, s,
            stock=stock, sector=sector, macro=macro, detail=detail)

    # ------------------------------------------------------------ 조회 보조
    def keys(self, group: str, start: str = None, period: int = None) -> list:
        """그 기간에 데이터가 있는 키 목록."""
        start = start or datetime.now().strftime("%Y-%m-%d")
        w_start, w_end = indicator.window(start, period or self.settings.period_days)
        return db.group_keys(self.conn, group.upper(), w_start, w_end)

    def stats(self) -> dict:
        """DB 전체 요약."""
        return db.overview(self.conn)

    def clusters(self, start: str, end: str) -> list:
        return db.cluster_stats(self.conn, start, end)

    def pending_news(self, limit: int = 100) -> list:
        """아직 AI 분류가 안 된 기사 목록(§0-12, 관리자 페이지 "미분석 뉴스")."""
        return db.pending_news(self.conn, limit=limit)

    def pending_count(self) -> int:
        return db.count_pending(self.conn)

    def analyzed_news(self, limit: int = 100) -> list:
        """이미 AI 분류된 기사 목록(§0-12, 관리자 페이지 "분석된 뉴스"). 최신순."""
        return db.list_analyzed_news(self.conn, limit=limit)

    def clusters_for_key(self, group: str, key: str, start: str, end: str) -> list:
        """특정 종목/섹터/거시지표 키에 연결된 클러스터 목록(기간 내) — "종목/섹터/거시로부터
        관련 클러스터 탐색"용(nemo-stock 관리자 페이지)."""
        return db.group_cluster_rows(self.conn, group.upper(), key, start, end)

    def keys_in_range(self, group: str, start: str, end: str) -> list:
        """기간 내에 데이터가 있는 키(종목/섹터/거시지표명) 목록 — 관리자 페이지에서 탐색할
        키를 고르는 드롭다운 소스로 쓴다."""
        return db.group_keys(self.conn, group.upper(), start, end)

    @staticmethod
    def groups() -> dict:
        """{"A": "종목 영향 지표", ...}"""
        return {g: name for g, (_, _, name) in GROUPS.items()}
