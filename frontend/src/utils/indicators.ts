/** 보조지표 순수 계산 함수. 종가(또는 필요한 배열)만 입력받아 클라이언트에서 계산한다
 * (백엔드는 OHLCV 원본만 제공, 지표 계산 자체는 저장/재계산 비용이 없어 프론트에서 수행). */

export function sma(values: number[], period: number): (number | null)[] {
  const out: (number | null)[] = []
  let sum = 0
  for (let i = 0; i < values.length; i++) {
    sum += values[i]
    if (i >= period) sum -= values[i - period]
    out.push(i >= period - 1 ? sum / period : null)
  }
  return out
}

export interface BollingerBands {
  upper: (number | null)[]
  mid: (number | null)[]
  lower: (number | null)[]
}

export function bollingerBands(values: number[], period = 20, mult = 2): BollingerBands {
  const mid = sma(values, period)
  const upper: (number | null)[] = []
  const lower: (number | null)[] = []
  for (let i = 0; i < values.length; i++) {
    const m = mid[i]
    if (m === null || i < period - 1) {
      upper.push(null)
      lower.push(null)
      continue
    }
    const window = values.slice(i - period + 1, i + 1)
    const variance = window.reduce((acc, v) => acc + (v - m) ** 2, 0) / period
    const sd = Math.sqrt(variance)
    upper.push(m + mult * sd)
    lower.push(m - mult * sd)
  }
  return { upper, mid, lower }
}

export function rsi(values: number[], period = 14): (number | null)[] {
  const out: (number | null)[] = new Array(values.length).fill(null)
  if (values.length < period + 1) return out

  let gainSum = 0
  let lossSum = 0
  for (let i = 1; i <= period; i++) {
    const diff = values[i] - values[i - 1]
    if (diff >= 0) gainSum += diff
    else lossSum -= diff
  }
  let avgGain = gainSum / period
  let avgLoss = lossSum / period
  out[period] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss)

  for (let i = period + 1; i < values.length; i++) {
    const diff = values[i] - values[i - 1]
    const gain = diff > 0 ? diff : 0
    const loss = diff < 0 ? -diff : 0
    avgGain = (avgGain * (period - 1) + gain) / period
    avgLoss = (avgLoss * (period - 1) + loss) / period
    out[i] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss)
  }
  return out
}
