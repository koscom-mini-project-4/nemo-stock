"""A/B/C 세 지표를 합쳐서 매매 판단으로 바꾸는 계층.

지표 자체(A/B/C)는 각각 독립적으로 t/n/f 를 낸다. 실제 매매는 셋을 같이 봐야 하는데,
"어떻게 합칠지"는 정해진 답이 없어서 세 가지 방식을 두고 고를 수 있게 했다.

  weighted     세 지표의 평균값을 가중평균한다. 기본값. (A 0.5 / B 0.3 / C 0.2)
               섹터·거시가 나빠도 종목 자체 호재가 크면 살 수 있다는 관점.
  vote         t=+1 / n=0 / f=-1 로 놓고 다수결. 값의 크기를 무시하고 방향만 본다.
               한 지표가 극단값을 내도 나머지 둘이 막아준다.
  stock_first  A(종목)가 t 또는 f 면 그대로 따르고, n 일 때만 B/C 를 본다.
               종목 뉴스가 가장 직접적인 신호라는 관점.

출력 형태(signal_style)도 세 가지다.
  tfn    t / n / f          (지표와 같은 표기)
  trade  BUY / HOLD / SELL  (매매 액션)
  score  숫자 그대로         (임계값 판정 없이 원점수)
"""
from . import indicator
from .db import GROUPS

TRADE_LABEL = {"t": "BUY", "n": "HOLD", "f": "SELL"}
VOTE_VALUE = {"t": 1, "n": 0, "f": -1}


def _style(verdict: str, score: float, style: str):
    if style == "trade":
        return TRADE_LABEL[verdict]
    if style == "score":
        return round(score, 6)
    return verdict


def combine(parts: dict, weights: dict, how: str, threshold: float) -> tuple:
    """A/B/C 결과 dict 를 하나의 (점수, 판정) 으로 합친다.

    parts: {"A": 지표결과, "B": ..., "C": ...} — 없는 그룹은 빠져 있어도 된다.
    """
    present = {g: r for g, r in parts.items() if r is not None}
    if not present:
        return 0.0, "n"

    if how == "vote":
        # 방향만 본다. 가중치는 표의 무게로 쓴다.
        total = sum(VOTE_VALUE[r["판정"]] * weights.get(g, 0) for g, r in present.items())
        wsum = sum(weights.get(g, 0) for g in present) or 1
        score = total / wsum
        # 표 결과는 -1~1 범위라 threshold 를 그대로 쓰면 너무 민감하다. 과반 기준.
        return score, ("t" if score > 0.5 else "f" if score < -0.5 else "n")

    if how == "stock_first":
        a = present.get("A")
        if a and a["판정"] != "n":
            return a["평균"], a["판정"]
        rest = {g: r for g, r in present.items() if g != "A"}
        if not rest:
            return (a["평균"] if a else 0.0), "n"
        wsum = sum(weights.get(g, 0) for g in rest) or 1
        score = sum(r["평균"] * weights.get(g, 0) for g, r in rest.items()) / wsum
        return score, indicator.verdict(score, threshold)

    # weighted (기본)
    wsum = sum(weights.get(g, 0) for g in present) or 1
    score = sum(r["평균"] * weights.get(g, 0) for g, r in present.items()) / wsum
    return score, indicator.verdict(score, threshold)


def decide(conn, start: str, period_days: int, settings, *,
           stock: str = None, sector: str = None, macro: str = None,
           detail: bool = True) -> dict:
    """종목/섹터/거시 키를 받아 A/B/C 를 계산하고 하나의 매매 판단으로 합친다.

    셋 중 준 것만 계산한다. 종목만 주면 A 만 보고 판단한다.
    """
    keys = {"A": stock, "B": sector, "C": macro}
    parts = {}
    for g, key in keys.items():
        if not key:
            continue
        parts[g] = indicator.compute(
            conn, g, key, start, period_days,
            threshold=settings.threshold,
            decay_base=settings.decay_base,
            include_zero=settings.include_zero,
            decay_from=settings.decay_from,
        )

    score, verdict = combine(parts, settings.weights, settings.combine,
                             settings.threshold)

    out = {
        "판단": _style(verdict, score, settings.signal_style),
        "점수": round(score, 6),
        "결합방식": settings.combine,
        "가중치": {g: settings.weights.get(g) for g in parts},
        "키": {name: keys[g] for g, name in
               (("A", "종목"), ("B", "섹터"), ("C", "거시지표")) if keys[g]},
        "기간": [start, period_days],
    }
    if detail:
        out["지표"] = {GROUPS[g][2]: parts[g] for g in parts}
    else:
        out["지표"] = {GROUPS[g][2]: {"평균": parts[g]["평균"],
                                      "판정": parts[g]["판정"],
                                      "클러스터수": parts[g]["클러스터수"]}
                       for g in parts}
    return out
