<script setup lang="ts">
/**
 * 종목 가격 차트 (TradingView lightweight-charts). 캔들스틱/라인 + 거래량 히스토그램 +
 * 이동평균선(MA5/MA20) 오버레이를 체크박스로 켜고 끌 수 있다. nemo-poc의
 * frontend/src/components/PriceChart.tsx와 동일한 로직을 Vue로 이식했다.
 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  LineSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts'
import type { PricePointOut } from '@/api/types'

const props = withDefaults(
  defineProps<{
    bars: PricePointOut[]
    /** 백테스트/일봉(실제 OHLC)은 캔들스틱, 단일 값만 있는 시계열은 라인이 자연스럽다. */
    mode?: 'candlestick' | 'line'
    height?: number
  }>(),
  { mode: 'candlestick', height: 260 },
)

const MA_PERIODS = [5, 20] as const
const MA_COLORS: Record<number, string> = { 5: '#f5a623', 20: '#4f7df3' }

function toChartTime(dateStr: string): Time {
  if (dateStr.includes('T')) {
    return Math.floor(new Date(dateStr).getTime() / 1000) as UTCTimestamp
  }
  return dateStr as Time
}

/** 단순 이동평균. 앞쪽 (period-1)개는 계산 불가하므로 null. */
function computeMA(closes: number[], period: number): (number | null)[] {
  const out: (number | null)[] = []
  let sum = 0
  for (let i = 0; i < closes.length; i++) {
    sum += closes[i]
    if (i >= period) sum -= closes[i - period]
    out.push(i >= period - 1 ? sum / period : null)
  }
  return out
}

const containerEl = ref<HTMLDivElement | null>(null)
const showVolume = ref(true)
const activeMAs = ref<Set<number>>(new Set(MA_PERIODS))

let chart: IChartApi | null = null
let priceSeries: ISeriesApi<'Candlestick'> | ISeriesApi<'Line'> | null = null
let volumeSeries: ISeriesApi<'Histogram'> | null = null
const maSeries = new Map<number, ISeriesApi<'Line'>>()

// 차트/시리즈는 컨테이너 마운트 시(모드가 바뀌면 재생성) 만든다. 색상은 CSS 변수를 읽어와
// 라이트/다크 테마를 그대로 따르게 한다.
function buildChart() {
  const container = containerEl.value
  if (!container) return

  const styles = getComputedStyle(document.documentElement)
  const textColor = styles.getPropertyValue('--text').trim() || '#1f2430'
  const borderColor = styles.getPropertyValue('--border').trim() || '#e2e4e9'

  chart = createChart(container, {
    height: props.height,
    layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor, fontSize: 11 },
    grid: { vertLines: { color: borderColor }, horzLines: { color: borderColor } },
    rightPriceScale: { borderColor },
    timeScale: { borderColor, timeVisible: true },
    autoSize: true,
  })

  priceSeries =
    props.mode === 'candlestick'
      ? chart.addSeries(CandlestickSeries, {
          upColor: '#dc2626',
          downColor: '#4f46e5',
          borderVisible: false,
          wickUpColor: '#dc2626',
          wickDownColor: '#4f46e5',
        })
      : chart.addSeries(LineSeries, { color: '#4f46e5', lineWidth: 2 })
  priceSeries.priceScale().applyOptions({ scaleMargins: { top: 0.1, bottom: 0.3 } })

  volumeSeries = chart.addSeries(HistogramSeries, {
    priceFormat: { type: 'volume' },
    priceScaleId: 'volume',
  })
  volumeSeries.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } })

  renderData()
}

function destroyChart() {
  chart?.remove()
  chart = null
  priceSeries = null
  volumeSeries = null
  maSeries.clear()
}

function renderData() {
  if (!chart || !priceSeries || !volumeSeries || props.bars.length === 0) return

  const sorted = [...props.bars].sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0))

  if (props.mode === 'candlestick') {
    ;(priceSeries as ISeriesApi<'Candlestick'>).setData(
      sorted.map((b) => ({ time: toChartTime(b.date), open: b.open, high: b.high, low: b.low, close: b.close })),
    )
  } else {
    ;(priceSeries as ISeriesApi<'Line'>).setData(sorted.map((b) => ({ time: toChartTime(b.date), value: b.close })))
  }

  volumeSeries.applyOptions({ visible: showVolume.value })
  volumeSeries.setData(
    sorted.map((b) => ({
      time: toChartTime(b.date),
      value: b.volume,
      color: b.close >= b.open ? 'rgba(220,38,38,0.5)' : 'rgba(79,70,229,0.5)',
    })),
  )

  const closes = sorted.map((b) => b.close)
  for (const period of MA_PERIODS) {
    let series = maSeries.get(period)
    if (!series) {
      series = chart.addSeries(LineSeries, {
        color: MA_COLORS[period] ?? '#888',
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      })
      maSeries.set(period, series)
    }
    const visible = activeMAs.value.has(period)
    series.applyOptions({ visible })
    if (visible) {
      const ma = computeMA(closes, period)
      const points: { time: Time; value: number }[] = []
      sorted.forEach((b, i) => {
        const v = ma[i]
        if (v !== null) points.push({ time: toChartTime(b.date), value: v })
      })
      series.setData(points)
    }
  }

  chart.timeScale().fitContent()
}

function toggleMA(period: number) {
  const next = new Set(activeMAs.value)
  if (next.has(period)) next.delete(period)
  else next.add(period)
  activeMAs.value = next
}

onMounted(buildChart)
onBeforeUnmount(destroyChart)

watch(() => props.mode, () => {
  destroyChart()
  buildChart()
})
watch([() => props.bars, showVolume, activeMAs], renderData, { deep: true })
</script>

<template>
  <div class="price-chart">
    <div class="price-chart-toggles">
      <label class="price-chart-toggle">
        <input v-model="showVolume" type="checkbox" />
        거래량
      </label>
      <label
        v-for="p in MA_PERIODS"
        :key="p"
        class="price-chart-toggle"
        :style="{ color: MA_COLORS[p] }"
      >
        <input type="checkbox" :checked="activeMAs.has(p)" @change="toggleMA(p)" />
        MA{{ p }}
      </label>
    </div>
    <p v-if="bars.length === 0" class="text-muted">표시할 시세 데이터가 없습니다.</p>
    <!-- 컨테이너는 bars가 비어 있어도 항상 마운트해둔다 — 조건부로 마운트/언마운트하면
         autoSize(ResizeObserver)가 크기를 못 잡아 차트가 그려지지 않는다(nemo-poc에서
         실제로 겪은 버그, 같은 실수를 반복하지 않기 위한 주석). -->
    <div ref="containerEl" class="price-chart-canvas" :style="{ height: `${height}px` }" />
  </div>
</template>

<style scoped>
.price-chart {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.price-chart-toggles {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
}
.price-chart-toggle {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: var(--text);
  cursor: pointer;
  user-select: none;
}
.price-chart-canvas {
  width: 100%;
}
</style>
