<script setup lang="ts">
import { ref } from 'vue'
import type { NodeEventOut } from '@/api/types'

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
        <span v-if="evt.duration_ms != null" class="text-muted">{{ Math.round(evt.duration_ms) }}ms</span>
      </div>
    </div>

    <div v-if="selectedIndex !== null && events[selectedIndex]" class="debug-detail">
      <div v-if="events[selectedIndex].error" class="error mono">{{ events[selectedIndex].error }}</div>
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
