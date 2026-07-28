"""지표 계산용 순수 함수 모음.

모든 함수는 종가/거래량 등 숫자 리스트를 입력받아 지표 시계열(또는 스칼라)을 반환한다.
외부 의존성이 없어 단위 테스트로 기대값을 고정하기 쉽다.

시계열 반환 함수는 입력 bar와 길이가 같은 리스트를 돌려주며, 계산에 필요한
관측치가 부족한 앞부분은 None으로 채운다(정렬 유지 → series[-1]=현재, series[-2]=직전).
"""

from __future__ import annotations

import math

Number = float


def mean(values: list[float]) -> float:
    if not values:
        raise ValueError("mean(): 빈 리스트")
    return sum(values) / len(values)


def stddev(values: list[float], sample: bool = True) -> float:
    """표준편차. sample=True면 표본 표준편차(ddof=1)."""
    n = len(values)
    if n < 2:
        return 0.0
    m = mean(values)
    denom = n - 1 if sample else n
    var = sum((v - m) ** 2 for v in values) / denom
    return math.sqrt(var)


def sma_series(values: list[float], window: int) -> list[float | None]:
    """단순이동평균 시계열."""
    if window <= 0:
        raise ValueError("window는 1 이상이어야 합니다.")
    out: list[float | None] = []
    for i in range(len(values)):
        if i + 1 < window:
            out.append(None)
        else:
            out.append(mean(values[i + 1 - window : i + 1]))
    return out


def ema_series(values: list[float], window: int) -> list[float | None]:
    """지수이동평균 시계열. 초기값은 첫 window개의 SMA로 시드한다."""
    if window <= 0:
        raise ValueError("window는 1 이상이어야 합니다.")
    out: list[float | None] = [None] * len(values)
    if len(values) < window:
        return out
    k = 2.0 / (window + 1)
    prev = mean(values[:window])
    out[window - 1] = prev
    for i in range(window, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi_series(closes: list[float], window: int = 14) -> list[float | None]:
    """Wilder RSI 시계열."""
    n = len(closes)
    out: list[float | None] = [None] * n
    if n <= window:
        return out
    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, n):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    # gains[i]는 closes[i+1] 시점의 변화 → 첫 RSI는 index=window에 위치
    avg_gain = mean(gains[:window])
    avg_loss = mean(losses[:window])

    def _rsi(g: float, ll: float) -> float:
        if ll == 0:
            return 100.0
        rs = g / ll
        return 100.0 - (100.0 / (1.0 + rs))

    out[window] = _rsi(avg_gain, avg_loss)
    for i in range(window + 1, n):
        avg_gain = (avg_gain * (window - 1) + gains[i - 1]) / window
        avg_loss = (avg_loss * (window - 1) + losses[i - 1]) / window
        out[i] = _rsi(avg_gain, avg_loss)
    return out


def macd_series(
    closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """(MACD선, 시그널선, 히스토그램) 시계열."""
    ema_fast = ema_series(closes, fast)
    ema_slow = ema_series(closes, slow)
    macd_line: list[float | None] = [
        (f - s) if (f is not None and s is not None) else None for f, s in zip(ema_fast, ema_slow)
    ]
    # 시그널선은 macd_line의 EMA(None 구간 제외 후 정렬 복원)
    valid = [(i, v) for i, v in enumerate(macd_line) if v is not None]
    signal_line: list[float | None] = [None] * len(closes)
    if len(valid) >= signal:
        vals = [v for _, v in valid]
        sig = ema_series(vals, signal)
        for (idx, _), s in zip(valid, sig):
            signal_line[idx] = s
    hist: list[float | None] = [
        (m - s) if (m is not None and s is not None) else None for m, s in zip(macd_line, signal_line)
    ]
    return macd_line, signal_line, hist


def true_range(high: float, low: float, prev_close: float) -> float:
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def atr_series(
    highs: list[float], lows: list[float], closes: list[float], window: int = 14
) -> list[float | None]:
    """Wilder ATR 시계열."""
    n = len(closes)
    out: list[float | None] = [None] * n
    if n <= window:
        return out
    trs: list[float] = [0.0]  # index 0은 이전 종가가 없으므로 자리표시
    for i in range(1, n):
        trs.append(true_range(highs[i], lows[i], closes[i - 1]))
    atr = mean(trs[1 : window + 1])
    out[window] = atr
    for i in range(window + 1, n):
        atr = (atr * (window - 1) + trs[i]) / window
        out[i] = atr
    return out


def rolling_max(values: list[float], window: int) -> list[float | None]:
    out: list[float | None] = []
    for i in range(len(values)):
        if i + 1 < window:
            out.append(None)
        else:
            out.append(max(values[i + 1 - window : i + 1]))
    return out


def daily_returns(closes: list[float]) -> list[float]:
    """일간 수익률(비율). 길이 = len(closes)-1."""
    return [(closes[i] / closes[i - 1] - 1.0) for i in range(1, len(closes)) if closes[i - 1] != 0]


def max_drawdown_pct(closes: list[float]) -> float:
    """구간 최대낙폭(양수 %). 예: 12.5 = 고점 대비 -12.5%."""
    if not closes:
        return 0.0
    peak = closes[0]
    mdd = 0.0
    for c in closes:
        if c > peak:
            peak = c
        if peak > 0:
            dd = (peak - c) / peak * 100.0
            mdd = max(mdd, dd)
    return mdd
