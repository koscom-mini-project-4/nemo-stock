"""Phase 2 — 시계열 누적 지표 산출.

수집 시점에 쌓인 단일 뉴스 점수(NewsSignalRecord)를 섹터·기간으로 묶어 알고리즘 노드가
소비할 '추세(Trend)' 지표를 만든다. PoC에서는 순수 파이썬으로 계산하며(단위 테스트로 기대값
고정), 데이터 규모가 커지면 동일 계약을 유지한 채 내부를 집계 테이블/SQL GROUP BY로 교체한다.

as_of(기준 시각)는 항상 명시적으로 주입해 결정성을 보장한다(노드는 context.timestamp를 사용).

지표 목록(투자 판단 용도):
  방향/강도 : sector_momentum, sentiment_ratio, symbol_news_stats, macro_sentiment_index
  추세      : momentum_change (모멘텀 가속도)
  쏠림/관심 : theme_zscore, buzz_zscore
  국면      : macro_risk_density, event_density
"""

from __future__ import annotations

import statistics
from collections.abc import Callable
from datetime import datetime, timedelta

from app.dao.base import NewsSignalRecord
from app.news_signals.impact import EVENT_WEIGHTS

RISK_EVENT_TYPES = ("Geopolitical_Risk", "Macro_Indicator")

# 정규화 기준(가장 파급력이 큰 이벤트 가중치). 이 값으로 나눠 -1.0 ~ +1.0 스케일을 만든다.
MAX_EVENT_WEIGHT = max(EVENT_WEIGHTS.values())


def _in_window(signals: list[NewsSignalRecord], as_of: datetime, days: int) -> list[NewsSignalRecord]:
    cutoff = as_of - timedelta(days=days)
    return [s for s in signals if cutoff <= s.published_at <= as_of]


def _daily_count_zscore(
    signals: list[NewsSignalRecord],
    as_of: datetime,
    lookback_days: int,
    predicate: Callable[[NewsSignalRecord], bool],
) -> float | None:
    """당일 건수를 최근 lookback_days일의 '일별 건수' 베이스라인과 비교한 Z-Score.

    표준편차가 0(변동 없음)이거나 데이터가 부족하면 None(=이상 신호 없음).
    """
    as_of_day = as_of.date()

    def count(day) -> int:
        return sum(1 for s in signals if s.published_at.date() == day and predicate(s))

    today = count(as_of_day)
    baseline = [count(as_of_day - timedelta(days=i)) for i in range(1, lookback_days + 1)]
    if len(baseline) < 2:
        return None
    std = statistics.pstdev(baseline)
    if std == 0:
        return None
    return (today - statistics.fmean(baseline)) / std


# ---------------------------------------------------------------------------
# 방향/강도
# ---------------------------------------------------------------------------


def sector_momentum(
    signals: list[NewsSignalRecord], sector: str, as_of: datetime, window_days: int = 7
) -> float | None:
    """주간 섹터 모멘텀 지수 = Σ(해당 섹터 sector_score) / 해당 섹터 뉴스 개수.

    양수(+)면 해당 섹터에 돈·관심이 쏠려 시장을 주도하는 상태. 해당 섹터 뉴스가 없으면 None.
    """
    rows = [s for s in _in_window(signals, as_of, window_days) if s.sector == sector]
    if not rows:
        return None
    return sum(s.sector_score for s in rows) / len(rows)


def sentiment_ratio(
    signals: list[NewsSignalRecord],
    as_of: datetime,
    sector: str | None = None,
    window_days: int = 7,
) -> float | None:
    """감성 우위도(Bull-Bear) = (호재 건수 − 악재 건수) / 전체 건수. 범위 -1.0 ~ +1.0.

    이벤트 가중치를 무시한 '순수 방향 투표'. 모멘텀(가중 평균)과 달리, 소수의 큰 뉴스가 아니라
    다수 의견의 방향 쏠림을 본다. sector=None이면 시장 전체. 뉴스가 없으면 None.
    """
    rows = _in_window(signals, as_of, window_days)
    if sector is not None:
        rows = [s for s in rows if s.sector == sector]
    if not rows:
        return None
    pos = sum(1 for s in rows if s.direction > 0)
    neg = sum(1 for s in rows if s.direction < 0)
    return (pos - neg) / len(rows)


def symbol_news_stats(
    signals: list[NewsSignalRecord], symbol: str, as_of: datetime, window_days: int = 7
) -> tuple[float | None, int]:
    """종목별 뉴스 점수 = 해당 종목 뉴스의 base_impact 평균, 그리고 뉴스 건수.

    섹터/시장 지표와 달리 '이 종목에 직접 붙은 뉴스'의 압력을 본다. 뉴스가 없으면 (None, 0).
    """
    rows = [s for s in _in_window(signals, as_of, window_days) if s.symbol == symbol]
    if not rows:
        return None, 0
    return sum(s.base_impact for s in rows) / len(rows), len(rows)


def symbol_direct_impact(
    signals: list[NewsSignalRecord], symbol: str, as_of: datetime, window_days: int = 7
) -> float | None:
    """종목 직접 영향도 = 그 종목에 직접 붙은 뉴스 base_impact 평균 / 최대 이벤트 가중치.

    symbol_news_stats(원점수 평균)와 달리 **-1.0 ~ +1.0으로 정규화**해, 이벤트 종류가 달라도
    같은 척도로 "이 종목에 얼마나 강한 뉴스가 직접 꽂혔는가"를 비교할 수 있게 한다.
    (예: 지정학 호재 1건 = 1.8/1.8 = 1.0, 단순 시황 호재 1건 = 0.3/1.8 ≈ 0.17)

    해당 종목 뉴스가 없으면 None(=신호 없음 → 조건에서 보수적으로 탈락).
    """
    rows = [s for s in _in_window(signals, as_of, window_days) if s.symbol == symbol]
    if not rows:
        return None
    return sum(s.base_impact for s in rows) / len(rows) / MAX_EVENT_WEIGHT


def sector_linked_impact(
    signals: list[NewsSignalRecord], sector: str, as_of: datetime, window_days: int = 7
) -> float | None:
    """업종 연관 영향도 = 섹터 영향이 실제로 켜진 뉴스들의 sector_score 평균 / 최대 이벤트 가중치.

    sector_momentum과 두 가지가 다르다.
      1) 분모가 '섹터 영향 플래그가 켜진 뉴스 수'다(sector_momentum은 해당 섹터 전체 뉴스 수라,
         섹터 영향이 없는 뉴스가 많을수록 값이 희석된다).
      2) -1.0 ~ +1.0으로 정규화되어 임계값(0.3/0.5/0.7)을 섹터 간 동일 기준으로 쓸 수 있다.

    즉 "그 업종을 실제로 움직이는 뉴스만 놓고 봤을 때 얼마나 우호적인가"를 본다.
    해당 섹터에 영향 뉴스가 없으면 None.
    """
    rows = [
        s
        for s in _in_window(signals, as_of, window_days)
        if s.sector == sector and s.sector_score != 0.0
    ]
    if not rows:
        return None
    return sum(s.sector_score for s in rows) / len(rows) / MAX_EVENT_WEIGHT


def macro_sentiment_index(
    signals: list[NewsSignalRecord], as_of: datetime, scope: str = "domestic", window_days: int = 5
) -> float | None:
    """거시 심리 지수 = 뉴스 1건당 평균 domestic_score(또는 overseas_score). Risk-on/off 게이지.

    scope="domestic"이면 국내(코스피/코스닥·거시경제) 심리, "overseas"이면 글로벌/지정학 심리.
    양수면 우호적, 음수면 위험회피 분위기. 윈도우에 뉴스가 없으면 None.
    """
    attr = "domestic_score" if scope == "domestic" else "overseas_score"
    rows = _in_window(signals, as_of, window_days)
    if not rows:
        return None
    return sum(getattr(s, attr) for s in rows) / len(rows)


# ---------------------------------------------------------------------------
# 추세(모멘텀의 변화)
# ---------------------------------------------------------------------------


def momentum_change(
    signals: list[NewsSignalRecord], sector: str, as_of: datetime, window_days: int = 7
) -> float | None:
    """섹터 모멘텀 가속도 = 최근 구간 모멘텀 − 직전 동일 구간 모멘텀.

    양수면 해당 섹터가 '가열'되는 중(추세 강화), 음수면 '식는' 중. 두 구간 중 하나라도
    뉴스가 없어 모멘텀을 못 구하면 None.
    """
    recent = sector_momentum(signals, sector, as_of, window_days)
    prior = sector_momentum(signals, sector, as_of - timedelta(days=window_days), window_days)
    if recent is None or prior is None:
        return None
    return recent - prior


# ---------------------------------------------------------------------------
# 쏠림/관심(빈도 기반)
# ---------------------------------------------------------------------------


def theme_zscore(
    signals: list[NewsSignalRecord], theme: str, as_of: datetime, lookback_days: int = 20
) -> float | None:
    """테마 쏠림 Z-Score = (당일 테마 언급 수 − 최근 N일 일평균) / 표준편차.

    특정 테마(예: HBM)가 평소보다 통계적으로 비정상적으로 많이 언급되는지 측정한다.
    """
    theme = theme.strip()
    return _daily_count_zscore(
        signals, as_of, lookback_days, lambda s: theme in (s.themes or [])
    )


def buzz_zscore(
    signals: list[NewsSignalRecord], as_of: datetime, sector: str | None = None, lookback_days: int = 20
) -> float | None:
    """뉴스 버즈 Z-Score = (당일 뉴스 건수 − 최근 N일 일평균) / 표준편차.

    방향과 무관하게 '관심(뉴스량)'이 평소 대비 급증했는지 본다. 급증은 종종 변동성/이벤트의
    전조다. sector=None이면 시장 전체, 지정 시 해당 섹터 뉴스량 기준.
    """
    if sector is None:
        predicate = lambda s: True  # noqa: E731
    else:
        predicate = lambda s: s.sector == sector  # noqa: E731
    return _daily_count_zscore(signals, as_of, lookback_days, predicate)


# ---------------------------------------------------------------------------
# 시장 국면(이벤트 밀도)
# ---------------------------------------------------------------------------


def event_density(
    signals: list[NewsSignalRecord],
    as_of: datetime,
    event_types: tuple[str, ...],
    window_days: int = 3,
) -> float:
    """이벤트 밀도(%) = (지정 event_type 뉴스 수 / 전체 뉴스 수) × 100.

    특정 성격의 이벤트가 뉴스 흐름을 얼마나 지배하는지. 예: M&A 붐, 실적 시즌, 정책 국면 탐지.
    윈도우에 뉴스가 없으면 0.0.
    """
    rows = _in_window(signals, as_of, window_days)
    if not rows:
        return 0.0
    hit = [s for s in rows if s.event_type in event_types]
    return len(hit) / len(rows) * 100.0


def macro_risk_density(
    signals: list[NewsSignalRecord], as_of: datetime, window_days: int = 3
) -> float:
    """단기 공포 지수(%) = 매크로/지정학 리스크 이벤트 밀도. 30~40% 초과면 공포 국면.

    event_density의 큐레이션된 특수 케이스(Geopolitical_Risk + Macro_Indicator).
    """
    return event_density(signals, as_of, RISK_EVENT_TYPES, window_days)


# ---------------------------------------------------------------------------
# 근거(§0-9) — "이 지표 점수를 만든 뉴스가 뭐였는지"
# ---------------------------------------------------------------------------


def top_contributor(
    signals: list[NewsSignalRecord],
    as_of: datetime,
    window_days: int,
    predicate: Callable[[NewsSignalRecord], bool],
    score_fn: Callable[[NewsSignalRecord], float] = lambda s: s.base_impact,
) -> NewsSignalRecord | None:
    """조건(predicate)에 맞는 신호 중 |score_fn| 절대값이 최대인 1건을 찾는다.

    각 지표 함수(sector_momentum 등)가 내부적으로 쓰는 것과 같은 윈도우/필터를 그대로 넘겨
    받아, "이 지표 점수를 만든 가장 큰 근거 뉴스"를 노드 출력에 보여줄 때 쓴다
    (app/nodes/ai/news_signal.py의 top_topic과 동일한 목적 — 그쪽은 클러스터 단위,
    이쪽은 개별 뉴스 단위). 일치하는 신호가 없으면 None.
    """
    rows = [s for s in _in_window(signals, as_of, window_days) if predicate(s)]
    if not rows:
        return None
    return max(rows, key=lambda s: abs(score_fn(s)))
