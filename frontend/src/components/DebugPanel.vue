<script setup lang="ts">
import { ref } from 'vue'
import { CheckCircle2, Hourglass, SkipForward, XCircle } from '@lucide/vue'
import type { NodeEventOut, NodeTypeSchema } from '@/api/types'
import { decisionsForEvent } from '@/utils/decisions'

const props = defineProps<{
  events: NodeEventOut[]
  playing: boolean
  nodeTypesByKey?: Map<string, NodeTypeSchema>
}>()

const selectedIndex = ref<number | null>(null)

function select(i: number) {
  selectedIndex.value = i
}

const STATUS_ICON = { running: Hourglass, success: CheckCircle2, error: XCircle, skipped: SkipForward }

const STATUS_LABEL: Record<string, string> = {
  running: '실행 중',
  success: '완료',
  error: '오류',
  skipped: '건너뜀',
}

function statusLabel(status: string): string {
  return STATUS_LABEL[status] ?? status
}

function nodeDisplayName(evt: NodeEventOut): string {
  return props.nodeTypesByKey?.get(evt.node_type)?.display_name ?? evt.node_type
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
        <span class="icon">
          <component :is="STATUS_ICON[evt.status] ?? CheckCircle2" :size="16" :stroke-width="2.2" />
        </span>
        <span class="status-label" :class="`status-label-${evt.status}`">{{ statusLabel(evt.status) }}</span>
        <span class="node-type">{{ nodeDisplayName(evt) }}</span>
        <span class="node-id mono text-muted">{{ evt.node_id }}</span>
        <span v-if="decisionSummary(evt)" class="decision-summary">{{ decisionSummary(evt) }}</span>
        <span v-if="evt.duration_ms != null" class="text-muted">{{ Math.round(evt.duration_ms) }}ms</span>
      </div>
    </div>

    <div v-if="selectedIndex !== null && events[selectedIndex]" class="debug-detail">
      <div v-if="events[selectedIndex].error" class="error mono">{{ events[selectedIndex].error }}</div>
      <div v-if="decisionsForEvent(events[selectedIndex]).length" class="detail-block">
        <div class="detail-label">판단 결과</div>
        <table class="decision-table">
          <tbody>
            <tr
              v-for="row in decisionsForEvent(events[selectedIndex])"
              :key="row.symbol"
              :class="row.pass ? 'decision-pass' : 'decision-fail'"
            >
              <td class="mono decision-symbol">{{ row.symbol }}</td>
              <td class="decision-badge">
                <CheckCircle2 v-if="row.pass" :size="13" :stroke-width="2.5" />
                <XCircle v-else :size="13" :stroke-width="2.5" />
                {{ row.pass ? '통과' : '탈락' }}
              </td>
              <td class="decision-reason">{{ row.reason }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="detail-block">
        <div class="detail-label">input</div>
        <pre class="mono">{{ JSON.stringify(events[selectedIndex].input_snapshot, null, 2) }}</pre>
      </div>
      <div class="detail-block">
        <div class="detail-label">output</div>
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
}

.debug-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.debug-item {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px 10px;
  padding: 9px 12px;
  border-left: 3px solid transparent;
  border-radius: 4px;
  cursor: pointer;
  font-size: 15px;
  transition: background 0.12s ease, border-color 0.12s ease;
}

.debug-item.status-running {
  border-left-color: var(--running);
}

.debug-item.status-success {
  border-left-color: var(--success);
}

.debug-item.status-error {
  border-left-color: var(--danger);
}

.debug-item.status-skipped {
  border-left-color: var(--border);
}

.debug-item:hover {
  background: var(--bg);
}

.debug-item.selected {
  background: color-mix(in srgb, var(--accent) 10%, var(--bg));
}

.icon {
  display: flex;
  align-items: center;
  color: var(--text-muted);
}

.status-running .icon {
  color: var(--running);
}

.status-success .icon {
  color: var(--success);
}

.status-error .icon {
  color: var(--danger);
}

.status-label {
  font-weight: 700;
  font-size: 14px;
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--bg);
}

.status-label-error {
  color: var(--danger);
}

.status-label-success {
  color: var(--success);
}

.status-label-running {
  color: var(--running);
}

.status-label-skipped {
  color: var(--text-muted);
}

.node-type {
  font-weight: 600;
}

.decision-summary {
  font-size: 13px;
  color: var(--text-muted);
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--bg);
}

.decision-table {
  width: 100%;
  table-layout: fixed;
  margin-top: 6px;
  border-collapse: collapse;
  font-size: 14px;
}

.decision-table .decision-symbol {
  width: 15%;
}

.decision-table .decision-badge {
  width: 12%;
  white-space: nowrap;
}

.decision-badge svg {
  vertical-align: -2px;
  margin-right: 3px;
}

.decision-table .decision-reason {
  width: 73%;
}

.decision-table td {
  padding: 7px 8px;
  border-bottom: 1px solid var(--border);
  vertical-align: top;
}

.decision-table tr:nth-child(even) {
  background: color-mix(in srgb, var(--bg) 60%, transparent);
}

.decision-table .decision-reason {
  color: var(--text-muted);
  line-height: 1.5;
  word-break: keep-all;
  overflow-wrap: break-word;
}

.decision-table .decision-pass .decision-badge {
  color: var(--success);
  font-weight: 600;
}

.decision-table .decision-fail .decision-badge {
  color: var(--danger);
  font-weight: 600;
}

.debug-detail {
  margin-top: 4px;
  padding: 14px 16px;
  border-top: 1px solid var(--border);
  background: color-mix(in srgb, var(--bg) 50%, transparent);
  border-radius: 0 0 6px 6px;
}

.detail-block {
  margin-bottom: 14px;
}

.detail-block:last-child {
  margin-bottom: 0;
}

.detail-label {
  font-size: 12.5px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--text-muted);
}

.detail-block pre {
  margin: 6px 0 0;
  background: var(--surface);
  border: 1px solid var(--border);
  padding: 10px;
  border-radius: 4px;
  max-height: 260px;
  overflow: auto;
  line-height: 1.5;
}

.debug-detail .error {
  color: var(--danger);
  margin-bottom: 8px;
}
</style>
