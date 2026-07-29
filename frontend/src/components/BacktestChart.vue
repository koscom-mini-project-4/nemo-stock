<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  BarController,
  BarElement,
  CategoryScale,
  Chart,
  Filler,
  Legend,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  ScatterController,
  Tooltip,
} from 'chart.js'
import { fetchBacktestNewsAll, fetchBacktestNewsSignal, fetchBacktestNewsUsed, fetchBacktestPrices } from '@/api/services'
import type { BacktestExplainSelection, BacktestResultOut, NewsMarkerOut, PricePointOut, TradeOut } from '@/api/types'
import { bollingerBands, rsi, sma } from '@/utils/indicators'
import { tradeStatusLabel } from '@/utils/labels'

Chart.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  LineController,
  BarController,
  ScatterController,
  Tooltip,
  Legend,
  Filler,
)

const props = defineProps<{ result: BacktestResultOut }>()
const emit = defineEmits<{
  select: [selection: BacktestExplainSelection]
  'select-day': [date: string]
  'open-trade': [trade: TradeOut]
}>()

const selectedSymbol = ref(props.result.universe[0] ?? '')
const intradayMode = ref(false)
const pricePoints = ref<PricePointOut[]>([])
const usedNews = ref<NewsMarkerOut[]>([])
const signalNews = ref<NewsMarkerOut[]>([])
const allNews = ref<NewsMarkerOut[]>([])
const showAllNews = ref(false)
const showMA = ref(true)
const showBollinger = ref(true)
const loading = ref(false)
const loadError = ref('')

const mainCanvas = ref<HTMLCanvasElement | null>(null)
const rsiCanvas = ref<HTMLCanvasElement | null>(null)
const volumeCanvas = ref<HTMLCanvasElement | null>(null)
const dragOverlay = ref<{ left: number; width: number } | null>(null)

let mainChart: Chart | null = null
let rsiChart: Chart | null = null
let volumeChart: Chart | null = null
let renderedLabels: string[] = []
let dragging = false
let dragStartIndex: number | null = null

async function loadSymbolData() {
  if (!selectedSymbol.value) return
  loading.value = true
  loadError.value = ''
  try {
    // 시간봉을 먼저 시도하고(짧은 최근 구간에만 존재, §0-2 실측 한계), 없으면 일봉으로 폴백한다.
    const intraday = await fetchBacktestPrices(props.result.id, selectedSymbol.value, 'minute60')
    intradayMode.value = intraday.length > 0
    pricePoints.value = intradayMode.value
      ? intraday
      : await fetchBacktestPrices(props.result.id, selectedSymbol.value, 'day')
    usedNews.value = await fetchBacktestNewsUsed(props.result.id, selectedSymbol.value)
    signalNews.value = await fetchBacktestNewsSignal(props.result.id, selectedSymbol.value)
    allNews.value = showAllNews.value ? await fetchBacktestNewsAll(props.result.id, selectedSymbol.value) : []
  } catch {
    loadError.value = '시세/뉴스 데이터를 불러오지 못했습니다.'
  } finally {
    loading.value = false
  }
  renderCharts()
}

async function toggleAllNews() {
  allNews.value = showAllNews.value ? await fetchBacktestNewsAll(props.result.id, selectedSymbol.value) : []
  renderCharts()
}

function buildDateMap<T>(dates: string[], values: T[]): Map<string, T> {
  const m = new Map<string, T>()
  dates.forEach((d, i) => m.set(d, values[i]))
  return m
}

// 일봉 모드에서는 라벨이 곧 날짜(YYYY-MM-DD)라 그대로 맞아떨어지지만, 시간봉 모드에서는 라벨이
// "YYYY-MM-DD HH:mm"이라 매매/뉴스/자산곡선처럼 "그날" 단위로 오는 데이터를 그 날짜의 봉에
// 맞춰 매핑해야 한다(둘 다 앞 10자만 비교하면 되므로 별도 분기 없이 동일 로직을 쓴다).
function dayPrefix(label: string): string {
  return label.slice(0, 10)
}

function buildDayAlignedSeries(labels: string[], dayValues: Map<string, number>): (number | null)[] {
  return labels.map((label) => dayValues.get(dayPrefix(label)) ?? null)
}

// 매매/뉴스처럼 "그 날짜에 표시할" 마커는 그날의 마지막 봉(라벨)에 꽂는다(라벨에 없는 날짜는 null).
function lastLabelForDay(labels: string[], dateStr: string): string | null {
  const prefix = dayPrefix(dateStr)
  let found: string | null = null
  for (const label of labels) {
    if (dayPrefix(label) === prefix) found = label
  }
  return found
}

function destroyCharts() {
  mainChart?.destroy()
  rsiChart?.destroy()
  volumeChart?.destroy()
  mainChart = rsiChart = volumeChart = null
}

// Chart.js의 혼합 데이터셋(line+scatter, 매매/뉴스 마커에 원본 객체를 실어 툴팁/클릭에서 꺼내 쓰는
// 패턴)은 공식 타입 정의로 정확히 표현하기 어려워 이 렌더 함수 내부에서만 any를 사용한다.
function renderCharts() {
  destroyCharts()
  if (!mainCanvas.value || !rsiCanvas.value || !volumeCanvas.value || pricePoints.value.length === 0) {
    renderedLabels = []
    return
  }

  const labels = pricePoints.value.map((p) => p.date)
  renderedLabels = labels
  const closes = pricePoints.value.map((p) => p.close)
  const volumes = pricePoints.value.map((p) => p.volume)

  const equityByDate = buildDateMap(
    props.result.equity_curve.map((e) => e.date),
    props.result.equity_curve.map((e) => e.equity),
  )
  const equitySeries = buildDayAlignedSeries(labels, equityByDate)

  const ma5 = sma(closes, 5)
  const ma20 = sma(closes, 20)
  const ma60 = sma(closes, 60)
  const boll = bollingerBands(closes, 20, 2)
  const rsiSeries = rsi(closes, 14)

  const datasets: any[] = [
    {
      type: 'line', label: '자산(equity)', data: equitySeries, yAxisID: 'yEquity',
      borderColor: '#4f46e5', backgroundColor: 'rgba(79,70,229,0.08)', pointRadius: 0, borderWidth: 1.5, tension: 0.15,
    },
    {
      type: 'line', label: `${selectedSymbol.value} 종가`, data: closes, yAxisID: 'yPrice',
      borderColor: '#0891b2', pointRadius: 0, borderWidth: 1.5, tension: 0.1,
    },
  ]

  if (showMA.value) {
    datasets.push(
      { type: 'line', label: 'MA5', data: ma5, yAxisID: 'yPrice', borderColor: '#f5a623', pointRadius: 0, borderWidth: 1, tension: 0.1 },
      { type: 'line', label: 'MA20', data: ma20, yAxisID: 'yPrice', borderColor: '#4f7df3', pointRadius: 0, borderWidth: 1, tension: 0.1 },
      { type: 'line', label: 'MA60', data: ma60, yAxisID: 'yPrice', borderColor: '#9333ea', pointRadius: 0, borderWidth: 1, tension: 0.1 },
    )
  }
  if (showBollinger.value) {
    datasets.push(
      { type: 'line', label: '볼린저 하단', data: boll.lower, yAxisID: 'yPrice', borderColor: 'rgba(107,114,128,0.35)', pointRadius: 0, borderWidth: 1, fill: false },
      { type: 'line', label: '볼린저 상단', data: boll.upper, yAxisID: 'yPrice', borderColor: 'rgba(107,114,128,0.35)', pointRadius: 0, borderWidth: 1, fill: datasets.length + 1, backgroundColor: 'rgba(107,114,128,0.10)' },
    )
  }

  // 한국 증시 관례: 매수(상승/이익) = 빨강, 매도(하락/손실) = 파랑. 범례에서도 매수/매도를
  // 구분해 보여주기 위해 하나의 '매매' 데이터셋 대신 두 개로 분리한다.
  const tradesForSymbol = props.result.trades
    .filter((t) => t.symbol === selectedSymbol.value)
    .map((t) => ({ label: lastLabelForDay(labels, t.date), trade: t }))
    .filter((d): d is { label: string; trade: TradeOut } => d.label !== null)
  const buyScatter = tradesForSymbol
    .filter((d) => d.trade.side === 'buy')
    .map((d) => ({ x: d.label, y: d.trade.price, trade: d.trade }))
  const sellScatter = tradesForSymbol
    .filter((d) => d.trade.side === 'sell')
    .map((d) => ({ x: d.label, y: d.trade.price, trade: d.trade }))
  datasets.push({
    type: 'scatter', label: '매수', yAxisID: 'yPrice', data: buyScatter, showLine: false,
    pointStyle: 'triangle', pointRadius: 7, pointBorderColor: '#fff', pointBorderWidth: 1,
    rotation: 0, pointBackgroundColor: '#d8394c',
  })
  datasets.push({
    type: 'scatter', label: '매도', yAxisID: 'yPrice', data: sellScatter, showLine: false,
    pointStyle: 'triangle', pointRadius: 7, pointBorderColor: '#fff', pointBorderWidth: 1,
    rotation: 180, pointBackgroundColor: '#155bd7',
  })

  const validCloses = closes.filter((c): c is number => c != null)
  const newsY = validCloses.length ? Math.min(...validCloses) : 0
  function newsScatter(news: NewsMarkerOut[]) {
    return news
      .map((n) => ({ label: lastLabelForDay(labels, n.date), news: n }))
      .filter((d): d is { label: string; news: NewsMarkerOut } => d.label !== null)
      .map((d) => ({ x: d.label, y: newsY, news: d.news }))
  }
  const usedNewsScatter = newsScatter(usedNews.value)
  datasets.push({
    type: 'scatter', label: '참고 뉴스', yAxisID: 'yPrice', data: usedNewsScatter, showLine: false,
    pointStyle: 'rectRot', pointRadius: 5, pointBackgroundColor: '#eab308', pointBorderColor: '#a16207',
  })
  // ai.news_signal(newsstock-lib) 데이터 소스 — data.news 기반 '참고 뉴스'와는 별개 파이프라인이라
  // 모양/색을 구분해서 같이 표시한다(둘 다 없을 수도, 둘 다 있을 수도 있음).
  const signalNewsScatter = newsScatter(signalNews.value)
  datasets.push({
    type: 'scatter', label: '뉴스 신호(newsstock)', yAxisID: 'yPrice', data: signalNewsScatter, showLine: false,
    pointStyle: 'triangle', pointRadius: 5, pointBackgroundColor: '#8b5cf6', pointBorderColor: '#5b21b6',
  })
  if (showAllNews.value) {
    const allNewsScatter = newsScatter(allNews.value)
    datasets.push({
      type: 'scatter', label: '전체 뉴스', yAxisID: 'yPrice', data: allNewsScatter, showLine: false,
      pointStyle: 'rectRot', pointRadius: 4, pointBackgroundColor: 'rgba(234,179,8,0.3)', pointBorderColor: 'rgba(161,98,7,0.3)',
    })
  }

  mainChart = new Chart(mainCanvas.value, {
    data: { labels, datasets },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      plugins: {
        legend: { display: true, labels: { boxWidth: 10, font: { size: 10 } } },
        tooltip: {
          callbacks: {
            label: (ctx: any) => {
              const raw = ctx.raw
              if (raw?.trade) {
                const t = raw.trade as TradeOut
                return `${t.side === 'buy' ? '매수' : '매도'} ${t.qty}주 @ ${t.price.toLocaleString()} (${tradeStatusLabel(t.status)})`
              }
              if (raw?.news) {
                return `뉴스: ${(raw.news as NewsMarkerOut).title}`
              }
              const y = ctx.parsed.y
              return `${ctx.dataset.label}: ${typeof y === 'number' ? y.toLocaleString() : y}`
            },
          },
        },
      },
      scales: {
        x: { ticks: { maxTicksLimit: 8, font: { size: 10 } } },
        yEquity: { type: 'linear', position: 'left', ticks: { font: { size: 10 }, callback: (v: any) => Number(v).toLocaleString() } },
        yPrice: { type: 'linear', position: 'right', grid: { drawOnChartArea: false }, ticks: { font: { size: 10 }, callback: (v: any) => Number(v).toLocaleString() } },
      },
    } as any,
  })
  // 개발 모드 한정 디버그 훅(E2E 테스트에서 캔버스 위 마커의 정확한 픽셀 좌표를 얻기 위함).
  // 프로덕션 빌드에는 포함되지 않는다(import.meta.env.DEV는 빌드 타임에 상수로 치환됨).
  if (import.meta.env.DEV) {
    ;(window as unknown as { __nemoMainChart?: Chart }).__nemoMainChart = mainChart
  }

  rsiChart = new Chart(rsiCanvas.value, {
    type: 'line',
    data: { labels, datasets: [{ label: 'RSI(14)', data: rsiSeries, borderColor: '#7c3aed', pointRadius: 0, borderWidth: 1.5, tension: 0.1 }] },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      plugins: { legend: { display: false } },
      scales: { x: { ticks: { display: false } }, y: { min: 0, max: 100, ticks: { font: { size: 10 }, stepSize: 50 } } },
    },
  })

  volumeChart = new Chart(volumeCanvas.value, {
    type: 'bar',
    data: { labels, datasets: [{ label: '거래량', data: volumes, backgroundColor: 'rgba(79,70,229,0.35)' }] },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { maxTicksLimit: 8, font: { size: 10 } } },
        y: { ticks: { font: { size: 10 }, callback: (v: any) => Number(v).toLocaleString() } },
      },
    },
  })
}

function canvasOffsetX(e: MouseEvent): number {
  const rect = mainCanvas.value!.getBoundingClientRect()
  return e.clientX - rect.left
}

function indexAtPixel(x: number): number | null {
  if (!mainChart || renderedLabels.length === 0) return null
  const value = (mainChart.scales.x as any).getValueForPixel(x)
  if (value === undefined) return null
  const idx = Math.round(value)
  if (idx < 0 || idx >= renderedLabels.length) return null
  return idx
}

function updateOverlay(a: number | null, b: number | null) {
  if (a === null || b === null || !mainChart) {
    dragOverlay.value = null
    return
  }
  const lo = Math.min(a, b)
  const hi = Math.max(a, b)
  const scale = mainChart.scales.x as any
  const left = scale.getPixelForValue(lo)
  const right = scale.getPixelForValue(hi)
  dragOverlay.value = { left: Math.min(left, right), width: Math.max(Math.abs(right - left), 2) }
}

function onMouseDown(e: MouseEvent) {
  if (!mainChart) return
  const elements = mainChart.getElementsAtEventForMode(e, 'nearest', { intersect: true } as any, true)
  const tradeHit = elements.find((el) => {
    const label = (mainChart!.data.datasets[el.datasetIndex] as any)?.label
    return label === '매수' || label === '매도'
  })
  if (tradeHit) {
    const point = (mainChart.data.datasets[tradeHit.datasetIndex].data as any[])[tradeHit.index]
    const trade = point.trade as TradeOut
    emit('select', { kind: 'point', symbol: selectedSymbol.value, date: trade.date })
    emit('select-day', trade.date)
    emit('open-trade', trade)
    return
  }
  dragging = true
  dragStartIndex = indexAtPixel(canvasOffsetX(e))
  updateOverlay(dragStartIndex, dragStartIndex)
}

function onMouseMove(e: MouseEvent) {
  if (!dragging || dragStartIndex === null) return
  updateOverlay(dragStartIndex, indexAtPixel(canvasOffsetX(e)) ?? dragStartIndex)
}

function onMouseUp(e: MouseEvent) {
  if (!dragging || dragStartIndex === null) {
    dragging = false
    return
  }
  const endIndex = indexAtPixel(canvasOffsetX(e)) ?? dragStartIndex
  const startIndex = dragStartIndex
  dragging = false
  dragStartIndex = null
  dragOverlay.value = null
  const lo = Math.min(startIndex, endIndex)
  const hi = Math.max(startIndex, endIndex)
  // renderedLabels는 시간봉 모드에서 "YYYY-MM-DD HH:mm"이라, AI 설명 API가 기대하는 순수
  // 날짜(date)로 잘라서 보낸다.
  emit('select', {
    kind: 'range',
    symbol: selectedSymbol.value,
    start_date: dayPrefix(renderedLabels[lo]),
    end_date: dayPrefix(renderedLabels[hi]),
  })
}

function onMouseLeaveWrap() {
  dragging = false
  dragStartIndex = null
  dragOverlay.value = null
}

watch(
  () => props.result.id,
  () => {
    selectedSymbol.value = props.result.universe[0] ?? ''
    loadSymbolData()
  },
)

onMounted(loadSymbolData)
onBeforeUnmount(destroyCharts)
</script>

<template>
  <div class="backtest-chart">
    <div class="controls">
      <label>
        종목
        <select v-model="selectedSymbol" @change="loadSymbolData">
          <option v-for="s in result.universe" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <label class="checkbox"><input v-model="showMA" type="checkbox" @change="renderCharts" /> 이동평균</label>
      <label class="checkbox"><input v-model="showBollinger" type="checkbox" @change="renderCharts" /> 볼린저밴드</label>
      <label class="checkbox"><input v-model="showAllNews" type="checkbox" @change="toggleAllNews" /> 전체 뉴스 표시(참고용)</label>
      <span class="interval-badge" :class="{ intraday: intradayMode }">
        {{ intradayMode ? '시간봉(60분)' : '일봉' }}
      </span>
    </div>
    <p class="text-muted hint">
      <span class="positive">▲매수</span> / <span class="negative">▼매도</span> 지점을 클릭하면 AI에게 물어볼 수 있고, 빈 구간을 드래그해 선택해도 물어볼 수 있습니다.
      시간봉은 최근 약 8거래일치만 제공되어(네이버 API 실측 한계) 그 기간을 벗어나면 자동으로
      일봉으로 표시됩니다.
    </p>
    <p v-if="loadError" class="error">{{ loadError }}</p>
    <p v-else-if="!loading && pricePoints.length === 0" class="text-muted">표시할 시세 데이터가 없습니다.</p>
    <div
      class="chart-wrap main"
      @mousedown="onMouseDown"
      @mousemove="onMouseMove"
      @mouseup="onMouseUp"
      @mouseleave="onMouseLeaveWrap"
    >
      <canvas ref="mainCanvas"></canvas>
      <div v-if="dragOverlay" class="drag-overlay" :style="{ left: dragOverlay.left + 'px', width: dragOverlay.width + 'px' }"></div>
    </div>
    <div class="chart-wrap sub">
      <canvas ref="rsiCanvas"></canvas>
    </div>
    <div class="chart-wrap sub">
      <canvas ref="volumeCanvas"></canvas>
    </div>
  </div>
</template>

<style scoped>
.backtest-chart {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 14px;
  font-size: 12.5px;
}

.controls label {
  display: flex;
  align-items: center;
  gap: 6px;
}

.controls .checkbox {
  gap: 4px;
}

.interval-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  background: var(--bg);
  color: var(--text-muted);
  border: 1px solid var(--border);
}

.interval-badge.intraday {
  background: color-mix(in srgb, #8b5cf6 12%, transparent);
  color: #8b5cf6;
  border-color: color-mix(in srgb, #8b5cf6 40%, transparent);
}

.hint {
  font-size: 11.5px;
  margin: 0;
}

.error {
  color: var(--danger);
  margin: 0;
  font-size: 12.5px;
}

.chart-wrap {
  position: relative;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--surface);
}

.chart-wrap.main {
  height: 300px;
  cursor: crosshair;
  user-select: none;
}

.chart-wrap.sub {
  height: 110px;
}

.drag-overlay {
  position: absolute;
  top: 0;
  bottom: 0;
  background: rgba(79, 70, 229, 0.15);
  border-left: 1px solid rgba(79, 70, 229, 0.5);
  border-right: 1px solid rgba(79, 70, 229, 0.5);
  pointer-events: none;
}
</style>
