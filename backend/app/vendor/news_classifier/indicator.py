"""A/B/C 그룹 영향 지표.

  A = 종목 영향 지표   (키: 종목명)
  B = 섹터 영향 지표   (키: 섹터명)
  C = 거시 영향 지표   (키: 거시지표명)

셋 다 계산 방법은 같다. 보는 테이블과 키만 다르다.

  1) 그룹 테이블에서 (키, 기간) 으로 뽑아 cluster_id 로 GROUP BY
     -> 클러스터별 count / 최초발생날짜 / strength
  2) 클러스터 점수 = strength * (1 - 0.3 * e^(1-count)) * 1/(d+1)
  3) 점수 합계를 클러스터 개수로 나눈 평균으로 판정
       평균 >=  0.1 -> "t"
       평균 <= -0.1 -> "f"
       그 사이       -> "n"
"""
import math
from datetime import datetime, timedelta

from . import db
from .config import DATE_FMT
from .db import GROUPS

DECAY_BASE = 0.3        # 계산식의 0.3
THRESHOLD = 0.1         # t/f 경계


def _parse(ts: str) -> datetime:
    """'YYYY-MM-DD HH:MM:SS' 또는 'YYYY-MM-DD' 둘 다 받는다."""
    ts = ts.strip()
    return datetime.strptime(ts if len(ts) > 10 else ts + " 00:00:00", DATE_FMT)


def window(start: str, period_days: int) -> tuple:
    """[시작날짜 00:00:00, 시작날짜+기간일 23:59:59]"""
    s = _parse(start[:10])
    e = s + timedelta(days=period_days)
    return s.strftime(DATE_FMT), e.strftime("%Y-%m-%d 23:59:59")


def cluster_score(strength: float, count: int, d: int,
                  decay_base: float = DECAY_BASE) -> float:
    """strength * (1 - 0.3 * e^(1-count)) * 1/(d+1)

    count=1 이면 (1 - 0.3*e^0) = 0.7 배, count 가 커질수록 1 배에 수렴한다.
    d 는 최신성 감쇠. d=0(기간 마지막 날 발생)이면 1 배.
    """
    return strength * (1 - decay_base * math.exp(1 - count)) * (1 / (d + 1))


def verdict(value: float, threshold: float = THRESHOLD) -> str:
    if value >= threshold:
        return "t"
    if value <= -threshold:
        return "f"
    return "n"


def _reference_day(w_start: str, w_end: str, mode: str):
    """d 를 재는 기준일."""
    if mode == "start":
        return _parse(w_start).date()
    if mode == "now":
        return datetime.now().date()
    return _parse(w_end).date()


def compute(conn, group: str, key: str, start: str, period_days: int, *,
            threshold: float = THRESHOLD, decay_base: float = DECAY_BASE,
            include_zero: bool = True, decay_from: str = "end") -> dict:
    """그룹 하나의 지표를 계산한다.

    group        : "A" | "B" | "C"
    key          : 종목명 / 섹터명 / 거시지표명
    include_zero : strength=0 클러스터를 평균의 분모에 넣을지.
                   False 면 "정보 없음"으로 보고 분모에서 제외한다.
    decay_from   : d 를 재는 기준 — "end"(기간 끝날) | "start"(시작일) | "now"(오늘)
    """
    group = group.upper()
    if group not in GROUPS:
        raise ValueError(f"group 은 A/B/C 중 하나여야 한다: {group!r}")
    _, _, name = GROUPS[group]

    w_start, w_end = window(start, period_days)
    ref_day = _reference_day(w_start, w_end, decay_from)

    clusters = []
    total = 0.0
    denom = 0
    for r in db.group_cluster_rows(conn, group, key, w_start, w_end):
        d = abs((ref_day - _parse(r["first_seen_at"]).date()).days)
        score = cluster_score(r["strength"], r["count"], d, decay_base)
        total += score
        if include_zero or r["strength"] != 0:
            denom += 1
        clusters.append({
            "클러스터id": r["cluster_id"],
            "대표제목": r["representative_title"],
            "최초발생날짜": r["first_seen_at"],
            "strength": r["strength"],
            "count": r["count"],
            "d": d,
            "점수": round(score, 6),
        })

    # 클러스터가 3개 묶였으면 3으로 나눈다. 하나도 없으면 0.
    average = total / denom if denom else 0.0

    return {
        "지표": name,
        "그룹": group,
        "키": key,
        "기간": [w_start, w_end],
        "클러스터수": len(clusters),
        "분모": denom,
        "클러스터": clusters,
        "합계": round(total, 6),
        "평균": round(average, 6),
        "판정": verdict(average, threshold),
    }


def stock_indicator(conn, stock: str, start: str, period_days: int) -> dict:
    """A: 종목 영향 지표"""
    return compute(conn, "A", stock, start, period_days)


def sector_indicator(conn, sector: str, start: str, period_days: int) -> dict:
    """B: 섹터 영향 지표"""
    return compute(conn, "B", sector, start, period_days)


def macro_indicator(conn, macro: str, start: str, period_days: int) -> dict:
    """C: 거시 영향 지표"""
    return compute(conn, "C", macro, start, period_days)


def compute_all_keys(conn, group: str, start: str, period_days: int) -> list:
    """기간 내에 데이터가 있는 모든 키에 대해 지표를 계산. 평균 내림차순."""
    w_start, w_end = window(start, period_days)
    keys = db.group_keys(conn, group.upper(), w_start, w_end)
    out = [compute(conn, group, k, start, period_days) for k in keys]
    out.sort(key=lambda r: r["평균"], reverse=True)
    return out
