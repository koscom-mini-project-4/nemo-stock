<script setup lang="ts">
import { ref } from 'vue'
import type { NodeDecision, NodeEventOut } from '@/api/types'

defineProps<{
  events: NodeEventOut[]
  playing: boolean
}>()

const selectedIndex = ref<number | null>(null)

function select(i: number) {
  selectedIndex.value = i
}

const STATUS_ICON: Record<string, string> = {
  running: '⏳',
  success: '✅',
  error: '⛔',
  skipped: '⏭️',
}

interface DecisionRow extends NodeDecision {
  symbol: string
}

// 필터형 노드(logic.if_else/logic.rank/risk.stop_loss/조건 내장 지표 노드)가 남긴
// 종목별 판단 근거를 output_snapshot.meta.decisions[node_id]에서 읽는다.
function decisionsFor(evt: NodeEventOut): DecisionRow[] {
  const meta = evt.output_snapshot?.meta as { decisions?: Record<string, Record<string, NodeDecision>> } | undefined
  const raw = meta?.decisions?.[evt.node_id]
  if (!raw) return []
  return Object.entries(raw).map(([symbol, decision]) => ({ symbol, ...decision }))
}

function decisionSummary(evt: NodeEventOut): string | null {
  const rows = decisionsFor(evt)
  if (rows.length === 0) return null
  const passed = rows.filter((r) => r.pass).length
  return `통과 ${passed} · 탈락 ${rows.length - passed}`
}

defineExpose({ select })
</script>

<template>
  <div class="debug-panel">
    <div class="debug-list">
      <p v-if="events.length === 0 && !playing" class="text-muted">"테스트 실행"으로 노드별 입출력을 확인하세요.</p>
      <div
        v-for="(evt, i) in events"
        :key="`${evt.node_id}-${evt.timestamp}-${i}`"
        class="debug-item"
        :class="[`status-${evt.status}`, { selected: selectedIndex === i }]"
        @click="select(i)"
      >
        <span class="icon">{{ STATUS_ICON[evt.status] ?? '•' }}</span>
        <span class="node-id mono">{{ evt.node_id }}</span>
        <span class="node-type text-muted">{{ evt.node_type }}</span>
        <span v-if="decisionSummary(evt)" class="decision-summary">{{ decisionSummary(evt) }}</span>
        <span v-if="evt.duration_ms != null" class="text-muted">{{ Math.round(evt.duration_ms) }}ms</span>
      </div>
    </div>

    <div v-if="selectedIndex !== null && events[selectedIndex]" class="debug-detail">
      <div v-if="events[selectedIndex].error" class="error mono">{{ events[selectedIndex].error }}</div>
      <div v-if="decisionsFor(events[selectedIndex]).length" class="detail-block">
        <div class="text-muted">판단 결과</div>
        <table class="decision-table">
          <tbody>
            <tr
              v-for="row in decisionsFor(events[selectedIndex])"
              :key="row.symbol"
              :class="row.pass ? 'decision-pass' : 'decision-fail'"
            >
              <td class="mono">{{ row.symbol }}</td>
              <td class="decision-badge">{{ row.pass ? '✅ 통과' : '⛔ 탈락' }}</td>
              <td class="decision-reason mono">{{ row.reason }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="detail-block">
        <div class="text-muted">input</div>
        <pre class="mono">{{ JSON.stringify(events[selectedIndex].input_snapshot, null, 2) }}</pre>
      </div>
      <div class="detail-block">
        <div class="text-muted">output</div>
        <pre class="mono">{{ JSON.stringify(events[selectedIndex].output_snapshot, null, 2) }}</pre>
      </div>
    </div>
  </div>
</template>

<style scoped>
.debug-panel {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
  overflow-y: auto;
}

.debug-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}

.debug-item:hover,
.debug-item.selected {
  background: var(--bg);
}

.status-error {
  color: var(--danger);
}

.status-success {
  color: var(--success);
}

.status-running {
  color: var(--running);
}

.decision-summary {
  font-size: 11px;
  color: var(--text-muted);
  padding: 1px 6px;
  border-radius: 10px;
  background: var(--bg);
}

.decision-table {
  width: 100%;
  margin-top: 4px;
  border-collapse: collapse;
  font-size: 12px;
}

.decision-table td {
  padding: 4px 6px;
  border-bottom: 1px solid var(--border);
  vertical-align: top;
}

.decision-table .decision-badge {
  white-space: nowrap;
}

.decision-table .decision-reason {
  color: var(--text-muted);
}

.decision-table .decision-pass .decision-badge {
  color: var(--success);
}

.decision-table .decision-fail .decision-badge {
  color: var(--danger);
}

.detail-block {
  margin-bottom: 8px;
}

.detail-block pre {
  margin: 4px 0 0;
  background: var(--bg);
  padding: 8px;
  border-radius: 6px;
  max-height: 180px;
  overflow: auto;
}

.debug-detail .error {
  color: var(--danger);
  margin-bottom: 8px;
}
</style>
