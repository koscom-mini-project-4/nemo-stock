<script setup lang="ts">
import { ref } from 'vue'
import type { NodeEventOut } from '@/api/types'
import { decisionsForEvent } from '@/utils/decisions'

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

function decisionSummary(evt: NodeEventOut): string | null {
  const rows = decisionsForEvent(evt)
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
      <div v-if="decisionsForEvent(events[selectedIndex]).length" class="detail-block">
        <div class="text-muted">판단 결과</div>
        <table class="decision-table">
          <tbody>
            <tr
              v-for="row in decisionsForEvent(events[selectedIndex])"
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
