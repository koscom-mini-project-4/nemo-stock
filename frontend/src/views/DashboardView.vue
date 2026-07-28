<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  deleteWorkflow,
  fetchAccountSummary,
  fetchPrices,
  fetchWorkflows,
  fetchWorkflowTemplates,
  updateWorkflow,
} from '@/api/services'
import type { AccountSummaryOut, PricePointOut, WorkflowOut, WorkflowTemplateOut } from '@/api/types'
import { useDraftStore } from '@/stores/draft'
import PriceChart from '@/components/PriceChart.vue'

const workflows = ref<WorkflowOut[]>([])
const templates = ref<WorkflowTemplateOut[]>([])
const account = ref<AccountSummaryOut | null>(null)
const priceSeries = ref<Record<string, PricePointOut[]>>({})
const loading = ref(true)
const router = useRouter()
const draftStore = useDraftStore()

async function load() {
  loading.value = true
  try {
    const [wf, acc, tpl] = await Promise.all([
      fetchWorkflows(),
      fetchAccountSummary().catch(() => null),
      fetchWorkflowTemplates().catch(() => []),
    ])
    workflows.value = wf
    account.value = acc
    templates.value = tpl
    await loadPriceSeries(acc)
  } finally {
    loading.value = false
  }
}

/** 보유 종목별 최근 90일 시세를 병렬로 조회한다. 종목 하나가 실패해도 나머지 차트는 보인다. */
async function loadPriceSeries(acc: AccountSummaryOut | null) {
  if (!acc || acc.positions.length === 0) {
    priceSeries.value = {}
    return
  }
  const entries = await Promise.all(
    acc.positions.map(async (p) => {
      try {
        return [p.symbol, await fetchPrices(p.symbol, 90)] as const
      } catch {
        return [p.symbol, []] as const
      }
    }),
  )
  priceSeries.value = Object.fromEntries(entries)
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

function useTemplate(template: WorkflowTemplateOut) {
  draftStore.setDraft(template.name, template.graph)
  router.push('/strategies/new')
}

function statusLabel(status: string) {
  return { draft: '초안', active: '실행 중', inactive: '중지' }[status] || status
}

function formatMoney(value: number) {
  return Math.round(value).toLocaleString()
}

onMounted(load)
</script>

<template>
  <div class="dashboard">
    <div class="dashboard-header">
      <h1>전략 대시보드</h1>
      <div class="actions">
        <RouterLink class="btn" to="/ai/generate">AI로 전략 생성</RouterLink>
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
          <div class="kpi-value">{{ account ? formatMoney(account.cash) : '—' }}</div>
        </div>
        <div class="card kpi-card">
          <div class="kpi-label">평가자산(equity)</div>
          <div class="kpi-value">{{ account ? formatMoney(account.equity) : '—' }}</div>
        </div>
        <div class="card kpi-card">
          <div class="kpi-label">보유 종목 수</div>
          <div class="kpi-value">{{ account ? account.positions.length : '—' }}</div>
        </div>
      </div>

      <section v-if="account && account.positions.length > 0">
        <h2>보유 종목 시세</h2>
        <div class="price-grid">
          <div v-for="pos in account.positions" :key="pos.symbol" class="card price-card">
            <div class="price-card-head">
              <span class="price-card-symbol">{{ pos.symbol }}</span>
              <span class="text-muted">{{ pos.qty }}주 · 평단가 {{ formatMoney(pos.avg_price) }}</span>
            </div>
            <PriceChart :bars="priceSeries[pos.symbol] ?? []" mode="candlestick" :height="200" />
          </div>
        </div>
      </section>

      <section>
        <h2>템플릿으로 시작하기</h2>
        <p v-if="templates.length === 0" class="text-muted">불러올 템플릿이 없습니다.</p>
        <div v-else class="template-grid">
          <div v-for="tpl in templates" :key="tpl.id" class="card template-card">
            <h3>{{ tpl.name }}</h3>
            <p class="text-muted">{{ tpl.description }}</p>
            <button class="btn btn-primary" type="button" @click="useTemplate(tpl)">이 템플릿으로 시작하기</button>
          </div>
        </div>
      </section>

      <section>
        <h2>내 전략 ({{ workflows.length }})</h2>
        <p v-if="workflows.length === 0" class="text-muted">
          아직 전략이 없습니다. 위 템플릿이나 "새 전략 만들기"로 시작하세요.
        </p>

        <div v-else class="workflow-grid">
          <div v-for="wf in workflows" :key="wf.id" class="card workflow-card">
            <div class="workflow-card-head">
              <RouterLink :to="`/strategies/${wf.id}`" class="workflow-name">{{ wf.name }}</RouterLink>
              <span :class="['badge', `badge-${wf.status}`]">{{ statusLabel(wf.status) }}</span>
            </div>
            <p class="text-muted">
              노드 {{ wf.graph.nodes.length }}개 · 주기 {{ wf.schedule_interval_sec }}초 · 수정 {{ new Date(wf.updated_at).toLocaleString() }}
            </p>
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

.template-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 14px;
}

.template-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.template-card h3 {
  margin: 0;
  font-size: 15px;
}

.template-card p {
  flex: 1;
  margin: 0;
  line-height: 1.5;
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
}

.workflow-name {
  font-weight: 600;
  text-decoration: none;
  color: var(--text);
}

.workflow-card-actions {
  display: flex;
  gap: 6px;
  margin-top: 4px;
}
</style>
