<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  addWatchlistItem,
  deletePosition,
  deleteWorkflow,
  fetchAccountSummary,
  fetchPrices,
  fetchWatchlist,
  fetchWorkflowPnlSummary,
  fetchWorkflows,
  removeWatchlistItem,
  updateWorkflow,
  upsertPosition,
} from '@/api/services'
import type { AccountSummaryOut, PricePointOut, WatchlistItemOut, WorkflowOut, WorkflowPnlOut } from '@/api/types'
import { useSymbolMasterStore } from '@/stores/symbolMaster'
import { formatDateTimeKst, formatKrw } from '@/utils/format'
import { formatSignedKrw, formatSignedPct, pnlClass } from '@/utils/pnl'
import { workflowStatusLabel as statusLabel } from '@/utils/labels'
import PriceChart from '@/components/PriceChart.vue'
import PositionEditModal from '@/components/PositionEditModal.vue'
import SymbolAutocomplete from '@/components/SymbolAutocomplete.vue'

const workflows = ref<WorkflowOut[]>([])
const account = ref<AccountSummaryOut | null>(null)
const watchlist = ref<WatchlistItemOut[]>([])
const priceSeries = ref<Record<string, PricePointOut[]>>({})
const workflowPnl = ref<Record<string, WorkflowPnlOut>>({})
const loading = ref(true)
const router = useRouter()
const symbolMaster = useSymbolMasterStore()

// 수익률(%) <-> 수익금액(원) 표시 토글. 카드/배지를 클릭한 항목만 개별적으로 전환된다(예:
// "wf:<id>", "pos:<symbol>", "equity"). Set이라 Vue 3 반응성이 add/delete/has 전부에 걸린다.
const amountMode = reactive(new Set<string>())
function toggleAmountMode(key: string) {
  if (amountMode.has(key)) amountMode.delete(key)
  else amountMode.add(key)
}

async function load() {
  loading.value = true
  try {
    const [wf, acc, wl, pnl] = await Promise.all([
      fetchWorkflows(),
      fetchAccountSummary().catch(() => null),
      fetchWatchlist().catch(() => []),
      fetchWorkflowPnlSummary().catch(() => []),
      symbolMaster.ensureLoaded().then(() => undefined),
    ] as const)
    workflows.value = wf
    account.value = acc
    watchlist.value = wl
    workflowPnl.value = Object.fromEntries(pnl.map((p) => [p.workflow_id, p]))
    await loadPriceSeries()
  } finally {
    loading.value = false
  }
}

/** 평가자산 수익률: 계좌 초기 시드 현금(initial_cash) 대비 현재 평가자산. */
const equityReturn = computed(() => {
  const acc = account.value
  if (!acc || !acc.initial_cash) return null
  const amount = acc.equity - acc.initial_cash
  return { amount, pct: (amount / acc.initial_cash) * 100 }
})

/** 종목 시세별 수익률: 보유 평단가 대비 최근 종가(priceSeries 마지막 값). 시세가 아직 없으면 null. */
function positionReturn(symbol: string, qty: number, avgPrice: number): { amount: number; pct: number } | null {
  const series = priceSeries.value[symbol]
  if (!series || series.length === 0 || avgPrice <= 0) return null
  const current = series[series.length - 1].close
  return { amount: (current - avgPrice) * qty, pct: (current / avgPrice - 1) * 100 }
}

/** 보유 종목 + 관심종목 최근 90일 시세를 병렬로 조회한다. 종목 하나가 실패해도 나머지 차트는 보인다. */
async function loadPriceSeries() {
  const symbols = new Set<string>()
  account.value?.positions.forEach((p) => symbols.add(p.symbol))
  watchlist.value.forEach((w) => symbols.add(w.symbol))
  if (symbols.size === 0) {
    priceSeries.value = {}
    return
  }
  const entries = await Promise.all(
    [...symbols].map(async (symbol) => {
      try {
        return [symbol, await fetchPrices(symbol, 90)] as const
      } catch {
        return [symbol, []] as const
      }
    }),
  )
  priceSeries.value = Object.fromEntries(entries)
}

// 포지션 직접 추가/수정 — 테스트 실행 등으로 잘못 만들어진 포지션(예: 임의 문자열 종목코드)을
// 정정하거나, 실제 보유 종목을 수동으로 등록할 수 있게 한다.
const positionModalVisible = ref(false)
const positionModalMode = ref<'create' | 'edit'>('create')
const editingPosition = ref<{ symbol: string; qty: number; avgPrice: number } | null>(null)

function openCreatePosition() {
  positionModalMode.value = 'create'
  editingPosition.value = null
  positionModalVisible.value = true
}

function openEditPosition(symbol: string, qty: number, avgPrice: number) {
  positionModalMode.value = 'edit'
  editingPosition.value = { symbol, qty, avgPrice }
  positionModalVisible.value = true
}

async function savePosition(payload: { symbol: string; qty: number; avgPrice: number }) {
  await upsertPosition(payload.symbol, payload.qty, payload.avgPrice)
  positionModalVisible.value = false
  await load()
}

async function removePosition(symbol: string) {
  if (!confirm(`'${symbol}' 포지션을 삭제할까요?`)) return
  await deletePosition(symbol)
  await load()
}

// 관심종목: 보유 여부와 무관하게 추적하고 싶은 종목을 자유롭게 추가/삭제한다. 이미 보유
// 종목 카드로 표시 중인 심볼은 관심종목 목록에서 중복 표시하지 않는다.
const newWatchSymbol = ref('')
const heldSymbols = computed(() => new Set(account.value?.positions.map((p) => p.symbol) ?? []))
const watchlistOnly = computed(() => watchlist.value.filter((w) => !heldSymbols.value.has(w.symbol)))

async function addToWatchlist() {
  const symbol = newWatchSymbol.value.split(',')[0]?.trim()
  if (!symbol) return
  await addWatchlistItem(symbol)
  newWatchSymbol.value = ''
  await load()
}

async function removeFromWatchlist(symbol: string) {
  await removeWatchlistItem(symbol)
  await load()
}

// 관심종목 드래그 정렬: 서버에 순서를 저장하지 않고 화면 표시 순서만 바꾼다(새로고침 시 초기화).
const draggingWatchSymbol = ref<string | null>(null)
function onWatchDragStart(symbol: string) {
  draggingWatchSymbol.value = symbol
}
function onWatchDrop(targetSymbol: string) {
  const from = draggingWatchSymbol.value
  draggingWatchSymbol.value = null
  if (!from || from === targetSymbol) return
  const arr = watchlist.value
  const fromIdx = arr.findIndex((w) => w.symbol === from)
  const toIdx = arr.findIndex((w) => w.symbol === targetSymbol)
  if (fromIdx === -1 || toIdx === -1) return
  const [moved] = arr.splice(fromIdx, 1)
  arr.splice(toIdx, 0, moved)
}

async function toggleActive(wf: WorkflowOut) {
  const nextStatus = wf.status === 'active' ? 'inactive' : 'active'
  try {
    await updateWorkflow(wf.id, { status: nextStatus })
    await load()
  } catch {
    alert('상태 변경에 실패했습니다. 그래프 검증 오류가 있는지 확인하세요.')
  }
}

async function remove(wf: WorkflowOut) {
  if (!confirm(`'${wf.name}' 전략을 삭제할까요?`)) return
  await deleteWorkflow(wf.id)
  await load()
}

onMounted(load)
</script>

<template>
  <div class="dashboard">
    <div class="dashboard-header">
      <h1>전략 대시보드</h1>
      <div class="actions">
        <RouterLink class="btn btn-primary" to="/strategies/new">새 전략 만들기</RouterLink>
      </div>
    </div>

    <p v-if="loading" class="text-muted">불러오는 중...</p>

    <template v-else>
      <div class="kpi-grid">
        <div class="card kpi-card">
          <div class="kpi-label">실행 중 전략</div>
          <div class="kpi-value">{{ workflows.filter((w) => w.status === 'active').length }} / {{ workflows.length }}</div>
        </div>
        <div class="card kpi-card">
          <div class="kpi-label">계좌 현금</div>
          <div class="kpi-value">{{ account ? formatKrw(account.cash) : '—' }}</div>
        </div>
        <div class="card kpi-card">
          <div class="kpi-label">평가자산(equity)</div>
          <div class="kpi-value">{{ account ? formatKrw(account.equity) : '—' }}</div>
        </div>
        <div
          class="card kpi-card kpi-card-clickable"
          role="button"
          tabindex="0"
          title="클릭하면 수익률/수익금액 표시가 바뀝니다"
          @click="toggleAmountMode('equity')"
          @keydown.enter="toggleAmountMode('equity')"
        >
          <div class="kpi-label">평가자산 수익률</div>
          <div v-if="equityReturn" class="kpi-value" :class="pnlClass(equityReturn.amount)">
            {{ amountMode.has('equity') ? formatSignedKrw(equityReturn.amount) : formatSignedPct(equityReturn.pct) }}
          </div>
          <div v-else class="kpi-value">—</div>
        </div>
        <div class="card kpi-card">
          <div class="kpi-label">보유 종목 수</div>
          <div class="kpi-value">{{ account ? account.positions.length : '—' }}</div>
        </div>
      </div>

      <section>
        <h2>내 전략 ({{ workflows.length }})</h2>
        <p v-if="workflows.length === 0" class="text-muted">
          아직 전략이 없습니다. "새 전략 만들기"로 시작하세요.
        </p>

        <div v-else class="workflow-grid">
          <div v-for="wf in workflows" :key="wf.id" class="card workflow-card">
            <div class="workflow-card-head">
              <RouterLink :to="`/strategies/${wf.id}`" class="workflow-name">{{ wf.name }}</RouterLink>
              <span :class="['badge', `badge-${wf.status}`]">{{ statusLabel(wf.status) }}</span>
            </div>
            <p class="text-muted">
              노드 {{ wf.graph.nodes.length }}개 · 주기 {{ wf.schedule_interval_sec }}초 · 수정 {{ formatDateTimeKst(wf.updated_at) }}
            </p>
            <p
              v-if="workflowPnl[wf.id] && workflowPnl[wf.id].trade_count > 0"
              class="pnl-line"
              :class="pnlClass(workflowPnl[wf.id].total_pnl)"
              role="button"
              tabindex="0"
              title="클릭하면 수익률/수익금액 표시가 바뀝니다"
              @click="toggleAmountMode(`wf:${wf.id}`)"
              @keydown.enter="toggleAmountMode(`wf:${wf.id}`)"
            >
              {{
                amountMode.has(`wf:${wf.id}`) || workflowPnl[wf.id].return_pct === null
                  ? formatSignedKrw(workflowPnl[wf.id].total_pnl)
                  : formatSignedPct(workflowPnl[wf.id].return_pct!)
              }}
              <span class="text-muted pnl-trade-count">(체결 {{ workflowPnl[wf.id].trade_count }}건)</span>
            </p>
            <p v-else class="text-muted pnl-line">실거래 체결 이력 없음</p>
            <div class="workflow-card-actions">
              <button class="btn" @click="router.push(`/strategies/${wf.id}`)">편집</button>
              <button class="btn" @click="toggleActive(wf)">
                {{ wf.status === 'active' ? '중지' : '활성화' }}
              </button>
              <button class="btn btn-danger" @click="remove(wf)">삭제</button>
            </div>
          </div>
        </div>
      </section>

      <section>
        <div class="section-head">
          <h2>보유 종목 시세</h2>
          <button class="btn" type="button" @click="openCreatePosition">종목 직접 추가</button>
        </div>
        <p v-if="account && account.positions.length === 0" class="text-muted">
          보유 중인 종목이 없습니다. "종목 직접 추가"로 등록할 수 있습니다.
        </p>
        <div v-else-if="account" class="price-grid">
          <div v-for="pos in account.positions" :key="pos.symbol" class="card price-card">
            <div class="price-card-head">
              <span class="price-card-symbol">{{ symbolMaster.displayName(pos.symbol) }}</span>
              <div class="price-card-meta">
                <span class="text-muted">{{ pos.qty }}주 · 평단가 {{ formatKrw(pos.avg_price) }}</span>
                <span
                  v-if="positionReturn(pos.symbol, pos.qty, pos.avg_price)"
                  class="pnl-badge"
                  :class="pnlClass(positionReturn(pos.symbol, pos.qty, pos.avg_price)!.amount)"
                  role="button"
                  tabindex="0"
                  title="클릭하면 수익률/수익금액 표시가 바뀝니다"
                  @click="toggleAmountMode(`pos:${pos.symbol}`)"
                  @keydown.enter="toggleAmountMode(`pos:${pos.symbol}`)"
                >
                  {{
                    amountMode.has(`pos:${pos.symbol}`)
                      ? formatSignedKrw(positionReturn(pos.symbol, pos.qty, pos.avg_price)!.amount)
                      : formatSignedPct(positionReturn(pos.symbol, pos.qty, pos.avg_price)!.pct)
                  }}
                </span>
                <button
                  class="icon-btn"
                  type="button"
                  title="수정"
                  @click="openEditPosition(pos.symbol, pos.qty, pos.avg_price)"
                >
                  ✏️
                </button>
                <button class="icon-btn" type="button" title="삭제" @click="removePosition(pos.symbol)">
                  🗑️
                </button>
              </div>
            </div>
            <PriceChart :bars="priceSeries[pos.symbol] ?? []" mode="candlestick" :height="200" />
          </div>
        </div>
      </section>

      <section>
        <div class="section-head">
          <h2>관심 종목</h2>
          <div class="watch-add">
            <SymbolAutocomplete v-model="newWatchSymbol" placeholder="005930 또는 삼성전자" />
            <button class="btn" type="button" @click="addToWatchlist">추가</button>
          </div>
        </div>
        <p v-if="watchlistOnly.length === 0" class="text-muted">
          보유 여부와 무관하게 추적하고 싶은 종목을 추가해보세요.
        </p>
        <div v-else class="price-grid">
          <div
            v-for="item in watchlistOnly"
            :key="item.symbol"
            class="card price-card"
            :class="{ 'price-card-dragging': draggingWatchSymbol === item.symbol }"
            draggable="true"
            @dragstart="onWatchDragStart(item.symbol)"
            @dragover.prevent
            @drop="onWatchDrop(item.symbol)"
            @dragend="draggingWatchSymbol = null"
          >
            <div class="price-card-head">
              <span class="price-card-symbol">
                <span class="drag-handle" title="끌어서 순서 변경">⠿</span>
                {{ symbolMaster.displayName(item.symbol) }}
              </span>
              <div class="price-card-meta">
                <span class="badge">관심종목</span>
                <button class="icon-btn" type="button" title="삭제" @click="removeFromWatchlist(item.symbol)">
                  🗑️
                </button>
              </div>
            </div>
            <PriceChart :bars="priceSeries[item.symbol] ?? []" mode="candlestick" :height="200" />
          </div>
        </div>
      </section>

      <PositionEditModal
        :visible="positionModalVisible"
        :mode="positionModalMode"
        :symbol="editingPosition?.symbol"
        :qty="editingPosition?.qty"
        :avg-price="editingPosition?.avgPrice"
        @close="positionModalVisible = false"
        @save="savePosition"
      />
    </template>
  </div>
</template>

<style scoped>
.dashboard {
  padding: 24px;
  max-width: 1100px;
  margin: 0 auto;
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 28px;
}

.dashboard-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.dashboard-header h1 {
  font-size: 22px;
  margin: 0;
}

.actions {
  display: flex;
  gap: 8px;
}

section h2 {
  font-size: 16px;
  margin: 0 0 12px;
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}

.kpi-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.kpi-label {
  font-size: 12px;
  color: var(--text-muted);
}

.kpi-value {
  font-size: 22px;
  font-weight: 700;
}

.kpi-card-clickable {
  cursor: pointer;
  transition: border-color 0.15s;
}

.kpi-card-clickable:hover {
  border-color: var(--accent);
}

.pnl-badge {
  cursor: pointer;
  font-weight: 700;
  font-size: 13px;
  padding: 2px 6px;
  border-radius: 4px;
}

.pnl-badge:hover {
  background: var(--bg);
}

.pnl-line {
  margin: -2px 0 0;
  font-weight: 700;
  font-size: 13px;
  cursor: pointer;
  width: fit-content;
}

.pnl-trade-count {
  font-weight: 400;
}

.price-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 14px;
}

.price-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.price-card-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.price-card-symbol {
  font-weight: 700;
  font-size: 14px;
}

.price-card-dragging {
  opacity: 0.4;
}

.drag-handle {
  display: inline-block;
  margin-right: 4px;
  cursor: grab;
  color: var(--text-muted);
}

.price-card-meta {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.icon-btn {
  border: none;
  background: none;
  cursor: pointer;
  font-size: 13px;
  padding: 2px 4px;
  border-radius: 4px;
  line-height: 1;
}

.icon-btn:hover {
  background: var(--bg);
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;
}

.section-head h2 {
  margin: 0;
}

.watch-add {
  display: flex;
  align-items: center;
  gap: 6px;
}

.watch-add :deep(.symbol-autocomplete) {
  width: 220px;
}

.workflow-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 14px;
}

.workflow-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.workflow-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.workflow-name {
  font-weight: 600;
  text-decoration: none;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workflow-card-head .badge {
  flex-shrink: 0;
}

.workflow-card-actions {
  display: flex;
  gap: 6px;
  margin-top: 4px;
}
</style>
