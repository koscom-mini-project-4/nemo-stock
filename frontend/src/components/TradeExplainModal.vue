<script setup lang="ts">
import { ref, watch } from 'vue'
import { explainBacktest, fetchRun } from '@/api/services'
import type { NodeEventOut, TradeOut } from '@/api/types'
import { decisionForSymbol } from '@/utils/decisions'
import { tradeStatusLabel } from '@/utils/labels'

// 매매 마커(▲/▼) 클릭 시 뜨는 팝업. 두 단계로 보여준다:
// 1) 즉시(무료, AI 호출 없음): 그 거래일의 노드 실행 이벤트에서 trade.symbol에 해당하는
//    decisions(통과/탈락 사유, ai.news_signal이면 참고 뉴스 제목까지 포함)를 순서대로
//    세로 타임라인으로 보여준다 — DebugPanel.vue와 같은 데이터를 재사용(utils/decisions.ts).
// 2) 선택(버튼 클릭 시에만 AI 호출): "AI 종합 설명 요청"으로 POST /ai/backtest-explain을
//    호출해 자연어 요약을 받아온다(백엔드가 decisions/news_signal_clusters를 프롬프트에
//    포함하도록 보강되어 있어 뉴스 근거를 실제로 인용할 수 있다).
const props = defineProps<{
  visible: boolean
  trade: TradeOut | null
  workflowId: string
  backtestId: string
}>()

const emit = defineEmits<{ close: [] }>()

interface Step {
  nodeId: string
  nodeType: string
  status: NodeEventOut['status']
  pass?: boolean
  reason?: string
}

const loadingSteps = ref(false)
const loadError = ref('')
const steps = ref<Step[]>([])

const aiLoading = ref(false)
const aiError = ref('')
const aiReply = ref('')
const aiRequestedForRunId = ref('')

async function loadSteps() {
  if (!props.trade) return
  loadingSteps.value = true
  loadError.value = ''
  steps.value = []
  try {
    const run = await fetchRun(props.workflowId, props.trade.run_id)
    steps.value = run.events.map((evt) => {
      const decision = decisionForSymbol(evt, props.trade!.symbol)
      return {
        nodeId: evt.node_id,
        nodeType: evt.node_type,
        status: evt.status,
        pass: decision?.pass,
        reason: decision?.reason,
      }
    })
  } catch {
    loadError.value = '이 매매의 노드 실행 기록을 불러오지 못했습니다.'
  } finally {
    loadingSteps.value = false
  }
}

async function requestAiExplanation() {
  if (!props.trade || aiLoading.value) return
  // 같은 매매에 대해 다시 열었을 때 재호출하지 않도록 run_id 기준으로 캐시한다.
  if (aiRequestedForRunId.value === props.trade.run_id && aiReply.value) return
  aiLoading.value = true
  aiError.value = ''
  try {
    const result = await explainBacktest({
      backtest_id: props.backtestId,
      message: '이 매매가 왜 발생했는지 판단 근거(특히 뉴스가 있다면 그 내용)를 종합해서 설명해줘.',
      history: [],
      selection: { kind: 'point', symbol: props.trade.symbol, date: props.trade.date },
    })
    aiReply.value = result.reply
    aiRequestedForRunId.value = props.trade.run_id
  } catch (err) {
    const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
    aiError.value =
      typeof detail === 'string'
        ? detail
        : detail
          ? JSON.stringify(detail)
          : 'AI 설명 요청에 실패했습니다. OPENAI_API_KEY 설정을 확인하세요.'
  } finally {
    aiLoading.value = false
  }
}

watch(
  () => props.visible,
  (visible) => {
    if (visible) {
      aiReply.value = ''
      aiError.value = ''
      aiRequestedForRunId.value = ''
      loadSteps()
    }
  },
)

const STATUS_ICON: Record<string, string> = { running: '⏳', success: '✅', error: '⛔', skipped: '⏭️' }
</script>

<template>
  <div v-if="visible && trade" class="modal-backdrop" @click.self="emit('close')">
    <div class="card modal">
      <div class="modal-header">
        <h2>
          <span :class="trade.side === 'buy' ? 'positive' : 'negative'">{{ trade.side === 'buy' ? '매수' : '매도' }}</span>
          근거 —
          {{ trade.symbol }} · {{ trade.date }}
        </h2>
        <button class="btn" type="button" @click="emit('close')">닫기</button>
      </div>
      <p class="trade-summary text-muted">
        {{ trade.qty }}주 @ {{ trade.price.toLocaleString() }}원 · 상태 {{ tradeStatusLabel(trade.status) }}
        <span v-if="trade.realized_pnl != null" :class="trade.realized_pnl >= 0 ? 'positive' : 'negative'">
          · 실현손익 {{ trade.realized_pnl >= 0 ? '+' : '' }}{{ trade.realized_pnl.toLocaleString() }}원
        </span>
      </p>

      <p v-if="loadingSteps" class="text-muted">노드 실행 기록을 불러오는 중...</p>
      <p v-if="loadError" class="error">{{ loadError }}</p>

      <ol v-if="steps.length" class="timeline">
        <li
          v-for="(step, i) in steps"
          :key="`${step.nodeId}-${i}`"
          :class="['timeline-step', `status-${step.status}`, { 'has-decision': step.pass !== undefined }]"
        >
          <span class="timeline-icon">{{ STATUS_ICON[step.status] ?? '•' }}</span>
          <div class="timeline-body">
            <div class="timeline-title">
              <span class="mono">{{ step.nodeId }}</span>
              <span class="text-muted">{{ step.nodeType }}</span>
              <span v-if="step.pass !== undefined" :class="step.pass ? 'badge-pass' : 'badge-fail'">
                {{ step.pass ? '✅ 통과' : '⛔ 탈락' }}
              </span>
            </div>
            <div v-if="step.reason" class="timeline-reason">{{ step.reason }}</div>
          </div>
        </li>
      </ol>

      <div class="ai-section">
        <button class="btn btn-primary" type="button" :disabled="aiLoading" @click="requestAiExplanation">
          {{ aiLoading ? 'AI 설명 요청 중...' : 'AI 종합 설명 요청' }}
        </button>
        <p v-if="aiError" class="error">{{ aiError }}</p>
        <p v-if="aiReply" class="ai-reply">{{ aiReply }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
  padding: 24px;
}

.modal {
  width: 640px;
  max-width: 100%;
  max-height: 86vh;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.modal-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.modal-header h2 {
  margin: 0;
  font-size: 16px;
}

.trade-summary {
  margin: 0;
  font-size: 13px;
}

.error {
  color: var(--danger);
  margin: 0;
  font-size: 13px;
}

.timeline {
  list-style: none;
  margin: 4px 0;
  padding: 0;
  position: relative;
}

.timeline-step {
  display: flex;
  gap: 10px;
  padding: 6px 0;
  position: relative;
}

.timeline-step:not(:last-child)::before {
  content: '';
  position: absolute;
  left: 9px;
  top: 26px;
  bottom: -6px;
  width: 1px;
  background: var(--border);
}

.timeline-icon {
  flex-shrink: 0;
  width: 20px;
  text-align: center;
  font-size: 13px;
}

.timeline-body {
  flex: 1;
  min-width: 0;
}

.timeline-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  flex-wrap: wrap;
}

.timeline-reason {
  margin-top: 2px;
  font-size: 12.5px;
  color: var(--text-muted);
  line-height: 1.5;
}

.badge-pass,
.badge-fail {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--bg);
}

.badge-pass {
  color: var(--success);
}

.badge-fail {
  color: var(--danger);
}

.status-error .timeline-title {
  color: var(--danger);
}

.ai-section {
  border-top: 1px solid var(--border);
  padding-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ai-reply {
  margin: 0;
  font-size: 13px;
  line-height: 1.55;
  white-space: pre-wrap;
  background: var(--bg);
  border-radius: 4px;
  padding: 10px;
}
</style>
