<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { fetchBacktest, runBacktest } from '@/api/services'
import type { BacktestResultOut } from '@/api/types'
import EquityCurveChart from '@/components/EquityCurveChart.vue'

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

const result = ref<BacktestResultOut | null>(null)
const loading = ref(false)

function defaultEnd() {
  return new Date().toISOString().slice(0, 10)
}
function defaultStart() {
  const d = new Date()
  d.setMonth(d.getMonth() - 1)
  return d.toISOString().slice(0, 10)
}

async function loadExisting(id: string) {
  loading.value = true
  try {
    result.value = await fetchBacktest(id)
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
  try {
    const r = await runBacktest({
      workflow_id: workflowId.value,
      universe,
      start_date: startDate.value,
      end_date: endDate.value,
      initial_capital: initialCapital.value,
    })
    result.value = r
    router.replace(`/backtests/${r.id}`)
  } catch (err) {
    const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    runError.value = detail || '백테스트 실행에 실패했습니다.'
  } finally {
    running.value = false
  }
}

onMounted(() => {
  if (!isNew.value) {
    loadExisting(props.id)
  }
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
        <input v-model="universeText" type="text" placeholder="005930,000660" />
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
        대상 기간에 해당하는 일봉 데이터가 sqlite에 없으면 실행이 실패합니다. 먼저
        <code>POST /data/ingest/prices/manual</code> 또는 <code>/public</code>으로 데이터를 적재하세요.
      </p>
      <p v-if="runError" class="error">{{ runError }}</p>
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
        <h2>자산 곡선</h2>
        <EquityCurveChart :points="result.equity_curve" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.backtest-view {
  padding: 24px;
  max-width: 900px;
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
</style>
