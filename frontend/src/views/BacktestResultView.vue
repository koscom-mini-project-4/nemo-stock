<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch, type Ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Handle, Position, VueFlow, type Edge as VFEdge, type Node as VFNode } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import { fetchBacktest, fetchNodeTypes, fetchRun, fetchWorkflow, runBacktest } from '@/api/services'
import { subscribeRunEvents } from '@/api/ws'
import type { BacktestExplainSelection, BacktestResultOut, NodeEventOut, NodeTypeSchema, TradeOut } from '@/api/types'
import { graphToFlowElements, type FlowNodeData } from '@/utils/flowAdapter'
import BacktestChart from '@/components/BacktestChart.vue'
import BacktestAskPanel from '@/components/BacktestAskPanel.vue'
import BacktestProgressPanel from '@/components/BacktestProgressPanel.vue'
import DebugPanel from '@/components/DebugPanel.vue'
import TradeExplainModal from '@/components/TradeExplainModal.vue'
import SymbolAutocomplete from '@/components/SymbolAutocomplete.vue'

const props = defineProps<{ id: string }>()

const route = useRoute()
const router = useRouter()

const isNew = computed(() => props.id === 'new')

const workflowId = ref((route.query.workflow_id as string) || '')
const universeText = ref((route.query.universe as string) || '')
const startDate = ref(defaultStart())
const endDate = ref(defaultEnd())
const initialCapital = ref(10_000_000)
const running = ref(false)
const runError = ref('')
const progressEvents = ref<NodeEventOut[]>([])
let progressWs: WebSocket | null = null

function closeProgressWs() {
  progressWs?.close()
  progressWs = null
}

const result = ref<BacktestResultOut | null>(null)
const loading = ref(false)

// 일자별 노드 그래프 재생(§8 백테스트 결과 화면) — "테스트 실행"과 동일한 VueFlow 캔버스 +
// DebugPanel 조합을 재사용해 백테스트가 특정 거래일에 워크플로를 어떻게 실행했는지 보여준다.
const nodeTypes = ref<NodeTypeSchema[]>([])
const nodeTypesByKey = computed(() => new Map(nodeTypes.value.map((t) => [t.type, t])))
const flowNodes = ref([]) as Ref<VFNode<FlowNodeData>[]>
const flowEdges = ref([]) as Ref<VFEdge[]>
const selectedRunDate = ref('')
const debugEvents = ref<NodeEventOut[]>([])
const replaying = ref(false)
const replayError = ref('')

// 매매 시점 시각화 + AI 진단/수정 제안(BacktestChart/BacktestAskPanel) — 차트에서 매매 지점 클릭 또는
// 구간 드래그로 선택하면 그 근거로 AI에게 물어볼 수 있다.
const chartSelection = ref<BacktestExplainSelection | null>(null)

function onChartSelect(selection: BacktestExplainSelection) {
  chartSelection.value = selection
}

function onChartSelectDay(date: string) {
  if (result.value?.daily_runs.some((d) => d.date === date)) {
    selectedRunDate.value = date
    selectDay(date)
  }
}

// 매매 마커 클릭 시 뜨는 팝업(§ "왜 샀는지" 설명) — 위 select/select-day와는 별개로 추가된
// emit이라 기존 사이드 AskPanel/그래프 리플레이 동작은 그대로 유지된다.
const tradeModalTrade = ref<TradeOut | null>(null)
const tradeModalVisible = ref(false)

function onOpenTrade(trade: TradeOut) {
  tradeModalTrade.value = trade
  tradeModalVisible.value = true
}

function defaultEnd() {
  return new Date().toISOString().slice(0, 10)
}
function defaultStart() {
  const d = new Date()
  d.setMonth(d.getMonth() - 1)
  return d.toISOString().slice(0, 10)
}

function isWeekend(d: Date): boolean {
  const dow = d.getDay()
  return dow === 0 || dow === 6
}

function lastTradingDayOnOrBefore(d: Date): Date {
  const r = new Date(d)
  while (isWeekend(r)) r.setDate(r.getDate() - 1)
  return r
}

// ai.news_signal 노드가 포함된 워크플로는 백테스트 기간이 AI 호출량 제한(서버
// NEWS_SIGNAL_BACKTEST_MAX_DAYS)에 걸리기 쉬워, 기본 기간을 보수적으로 "최근 개장일 기준
// N일"로 자동 설정한다(공휴일 캘린더는 없어 주말만 건너뛰는 근사치).
function recentTradingDayRange(days: number): { start: string; end: string } {
  const end = lastTradingDayOnOrBefore(new Date())
  const start = new Date(end)
  let count = 1
  while (count < days) {
    start.setDate(start.getDate() - 1)
    if (!isWeekend(start)) count++
  }
  return { start: start.toISOString().slice(0, 10), end: end.toISOString().slice(0, 10) }
}

const NEWS_SIGNAL_DEFAULT_DAYS = 4
// 백엔드 app/api/routers/backtest.py::NEWS_SIGNAL_BACKTEST_MAX_DAYS와 값을 맞춘다(안내 문구 전용).
const NEWS_SIGNAL_MAX_DAYS = 14
const newsRangeAppliedFor = ref('')

async function applyNewsSignalDefaultRange(id: string) {
  if (!id || newsRangeAppliedFor.value === id) return
  try {
    const wf = await fetchWorkflow(id)
    const hasNewsSignal = wf.graph.nodes.some((n) => n.type === 'ai.news_signal')
    newsRangeAppliedFor.value = id
    if (hasNewsSignal) {
      const range = recentTradingDayRange(NEWS_SIGNAL_DEFAULT_DAYS)
      startDate.value = range.start
      endDate.value = range.end
    }
  } catch {
    // 워크플로를 못 불러와도 폼 자체는 계속 쓸 수 있어야 하므로 조용히 무시한다.
  }
}

watch(
  workflowId,
  (id) => {
    if (isNew.value) applyNewsSignalDefaultRange(id)
  },
  { immediate: true },
)

async function loadGraphAndFirstDay(r: BacktestResultOut) {
  if (nodeTypes.value.length === 0) {
    nodeTypes.value = await fetchNodeTypes()
  }
  const wf = await fetchWorkflow(r.workflow_id)
  const { nodes, edges } = graphToFlowElements(wf.graph, nodeTypesByKey.value)
  flowNodes.value = nodes
  flowEdges.value = edges
  if (r.daily_runs.length > 0) {
    selectedRunDate.value = r.daily_runs[0].date
    await selectDay(selectedRunDate.value)
  }
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function animateReplay(events: NodeEventOut[]) {
  flowNodes.value.forEach((n) => {
    n.class = undefined
  })
  debugEvents.value = []
  for (const evt of events) {
    const node = flowNodes.value.find((n) => n.id === evt.node_id)
    if (node) {
      node.class = `flow-status status-${evt.status}`
    }
    debugEvents.value = [...debugEvents.value, evt]
    // eslint-disable-next-line no-await-in-loop
    await sleep(evt.status === 'running' ? 160 : 90)
  }
}

async function selectDay(date: string) {
  if (!result.value) return
  const dr = result.value.daily_runs.find((d) => d.date === date)
  if (!dr) return
  replayError.value = ''
  replaying.value = true
  try {
    const run = await fetchRun(result.value.workflow_id, dr.run_id)
    await animateReplay(run.events)
  } catch {
    replayError.value = '해당 날짜의 실행 기록을 불러오지 못했습니다.'
  } finally {
    replaying.value = false
  }
}

async function loadExisting(id: string) {
  loading.value = true
  try {
    result.value = await fetchBacktest(id)
    if (result.value) await loadGraphAndFirstDay(result.value)
  } finally {
    loading.value = false
  }
}

async function submitRun() {
  runError.value = ''
  const universe = universeText.value
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
  if (!workflowId.value || universe.length === 0) {
    runError.value = '전략과 종목코드를 입력하세요.'
    return
  }
  running.value = true
  progressEvents.value = []
  // POST 응답을 기다리는 동안(§0-11) 거래일별 진행 상황을 실시간으로 보여준다 — 백엔드가
  // 이미 갖고 있던 EventBus/WS 인프라(app/api/ws.py)를 재사용하는 것이라, POST가 끝나기 전에
  // 먼저 구독을 걸어둬야 시작 이벤트부터 놓치지 않는다.
  const progressRunId = crypto.randomUUID()
  progressWs = subscribeRunEvents(progressRunId, (evt) => {
    progressEvents.value = [...progressEvents.value, evt]
  })
  try {
    const r = await runBacktest({
      workflow_id: workflowId.value,
      universe,
      start_date: startDate.value,
      end_date: endDate.value,
      initial_capital: initialCapital.value,
      progress_run_id: progressRunId,
    })
    result.value = r
    await loadGraphAndFirstDay(r)
    router.replace(`/backtests/${r.id}`)
  } catch (err) {
    const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    runError.value = detail || '백테스트 실행에 실패했습니다.'
  } finally {
    running.value = false
    closeProgressWs()
  }
}

onMounted(() => {
  if (!isNew.value) {
    loadExisting(props.id)
  }
})

onUnmounted(() => {
  closeProgressWs()
})
</script>

<template>
  <div class="backtest-view">
    <div v-if="isNew" class="card run-form">
      <h1>백테스트 실행</h1>
      <label>
        전략(workflow) ID
        <input v-model="workflowId" type="text" placeholder="workflow id" />
      </label>
      <label>
        대상 종목코드 (콤마 구분)
        <SymbolAutocomplete v-model="universeText" />
      </label>
      <div class="row">
        <label>
          시작일
          <input v-model="startDate" type="date" />
        </label>
        <label>
          종료일
          <input v-model="endDate" type="date" />
        </label>
        <label>
          초기자본
          <input v-model.number="initialCapital" type="number" min="0" step="100000" />
        </label>
      </div>
      <p class="text-muted">
        대상 기간에 해당하는 일봉 데이터가 sqlite에 없으면 실행 시 자동으로 수집합니다(네이버 증권
        시세, 종목당 최초 1회). 종목코드가 존재하지 않거나 데이터가 전혀 없는 기간이면 여전히
        실패할 수 있습니다. 뉴스 신호(ai.news_signal) 노드가 포함된 전략은 AI 호출량 제한 때문에
        기간이 최근 개장일 기준 {{ NEWS_SIGNAL_DEFAULT_DAYS }}일로 자동 설정됩니다(직접 수정 가능,
        최대 {{ NEWS_SIGNAL_MAX_DAYS }}일).
      </p>
      <p v-if="runError" class="error">{{ runError }}</p>
      <BacktestProgressPanel v-if="running" :events="progressEvents" />
      <button class="btn btn-primary" :disabled="running" @click="submitRun">
        {{ running ? '실행 중...' : '백테스트 실행' }}
      </button>
    </div>

    <p v-else-if="loading" class="text-muted">불러오는 중...</p>

    <div v-if="result" class="result">
      <h1>백테스트 결과</h1>
      <div class="metric-grid">
        <div class="card metric">
          <div class="text-muted">누적수익률</div>
          <div class="metric-value" :class="{ negative: result.total_return_pct < 0 }">
            {{ result.total_return_pct.toFixed(2) }}%
          </div>
        </div>
        <div class="card metric">
          <div class="text-muted">연환산수익률(CAGR)</div>
          <div class="metric-value">{{ result.cagr_pct.toFixed(2) }}%</div>
        </div>
        <div class="card metric">
          <div class="text-muted">최대낙폭(MDD)</div>
          <div class="metric-value negative">{{ result.mdd_pct.toFixed(2) }}%</div>
        </div>
        <div class="card metric">
          <div class="text-muted">변동성(연환산)</div>
          <div class="metric-value">{{ result.volatility_pct.toFixed(2) }}%</div>
        </div>
        <div class="card metric">
          <div class="text-muted">승률</div>
          <div class="metric-value">{{ result.win_rate_pct.toFixed(1) }}%</div>
        </div>
        <div class="card metric">
          <div class="text-muted">손익비</div>
          <div class="metric-value">{{ result.profit_loss_ratio?.toFixed(2) ?? '-' }}</div>
        </div>
        <div class="card metric">
          <div class="text-muted">거래횟수</div>
          <div class="metric-value">{{ result.trade_count }}</div>
        </div>
        <div class="card metric">
          <div class="text-muted">최종자산</div>
          <div class="metric-value">{{ Math.round(result.final_equity).toLocaleString() }}</div>
        </div>
      </div>

      <div class="card">
        <h2>매매 시점 · 시세 · 보조지표</h2>
        <div class="chart-ask-body">
          <div class="chart-pane">
            <BacktestChart
              :result="result"
              @select="onChartSelect"
              @select-day="onChartSelectDay"
              @open-trade="onOpenTrade"
            />
          </div>
          <div class="ask-pane">
            <BacktestAskPanel
              :backtest-id="result.id"
              :workflow-id="result.workflow_id"
              :selection="chartSelection"
            />
          </div>
        </div>
      </div>

      <div v-if="result.daily_runs.length > 0" class="card">
        <div class="replay-header">
          <h2>일자별 노드 그래프</h2>
          <select v-model="selectedRunDate" @change="selectDay(selectedRunDate)">
            <option v-for="dr in result.daily_runs" :key="dr.run_id" :value="dr.date">{{ dr.date }}</option>
          </select>
        </div>
        <p v-if="replayError" class="error">{{ replayError }}</p>
        <div class="replay-body">
          <div class="replay-canvas">
            <VueFlow
              v-model:nodes="flowNodes"
              v-model:edges="flowEdges"
              fit-view-on-init
              :nodes-draggable="false"
              :nodes-connectable="false"
              :default-viewport="{ zoom: 0.85 }"
            >
              <template #node-workflow="nodeProps">
                <div class="wf-node">
                  <Handle type="target" :position="Position.Left" />
                  <div class="wf-node-header">
                    <span class="wf-node-title">{{ nodeProps.data.displayName }}</span>
                    <span class="wf-node-type mono">{{ nodeProps.data.nodeType }}</span>
                  </div>
                  <Handle type="source" :position="Position.Right" />
                </div>
              </template>
              <Background pattern-color="var(--border)" :gap="16" />
              <Controls />
            </VueFlow>
          </div>
          <div class="replay-debug">
            <DebugPanel :events="debugEvents" :playing="replaying" />
          </div>
        </div>
      </div>

      <TradeExplainModal
        :visible="tradeModalVisible"
        :trade="tradeModalTrade"
        :workflow-id="result.workflow_id"
        :backtest-id="result.id"
        @close="tradeModalVisible = false"
      />
    </div>
  </div>
</template>

<style scoped>
.backtest-view {
  padding: 24px;
  max-width: 1200px;
  margin: 0 auto;
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

h1 {
  font-size: 20px;
  margin: 0 0 12px;
}

h2 {
  font-size: 15px;
  margin: 0 0 10px;
}

.run-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.run-form label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
  color: var(--text-muted);
}

.row {
  display: flex;
  gap: 10px;
}

.row label {
  flex: 1;
}

.error {
  color: var(--danger);
  margin: 0;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 10px;
}

.metric {
  text-align: center;
}

.metric-value {
  font-size: 20px;
  font-weight: 700;
  margin-top: 4px;
}

.metric-value.negative {
  color: var(--danger);
}

.chart-ask-body {
  display: flex;
  gap: 12px;
  align-items: stretch;
}

.chart-pane {
  flex: 1.6;
  min-width: 0;
}

.ask-pane {
  flex: 1;
  min-width: 280px;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}

.replay-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.replay-header select {
  font-size: 13px;
}

.replay-body {
  display: flex;
  gap: 12px;
  height: 380px;
}

.replay-canvas {
  flex: 1.4;
  min-width: 0;
  position: relative;
  border: 1px solid var(--border);
  border-radius: 8px;
}

.replay-canvas :deep(.vue-flow) {
  background: var(--bg);
}

.replay-debug {
  flex: 1;
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}

.wf-node {
  min-width: 160px;
  border: 1.5px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);
}

.wf-node-header {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 8px 10px;
}

.wf-node-title {
  font-size: 13px;
  font-weight: 600;
}

.wf-node-type {
  font-size: 10px;
  color: var(--text-muted);
}
</style>

<style>
/* Vue Flow가 내부적으로 렌더링하는 노드 DOM에는 scoped 속성이 적용되지 않으므로 전역 스타일로 정의한다.
   StrategyBuilderView.vue와 동일한 클래스명이지만, 이 뷰가 단독으로 로드될 수도 있어(빌더를 거치지
   않고 바로 백테스트 결과 페이지로 진입) 여기서도 동일하게 정의해둔다. */
.flow-status {
  border-radius: 8px;
  transition: box-shadow 0.2s, border-color 0.2s;
}

.flow-status.status-running {
  border-color: var(--running) !important;
  box-shadow: 0 0 0 3px rgba(234, 179, 8, 0.35);
  animation: nemo-pulse-backtest 0.7s ease-in-out infinite alternate;
}

.flow-status.status-success {
  border-color: var(--success) !important;
  box-shadow: 0 0 0 2px rgba(22, 163, 74, 0.25);
}

.flow-status.status-error {
  border-color: var(--danger) !important;
  box-shadow: 0 0 0 2px rgba(220, 38, 38, 0.3);
}

.flow-status.status-skipped {
  opacity: 0.5;
}

@keyframes nemo-pulse-backtest {
  from {
    box-shadow: 0 0 0 2px rgba(234, 179, 8, 0.25);
  }
  to {
    box-shadow: 0 0 0 6px rgba(234, 179, 8, 0.45);
  }
}
</style>
