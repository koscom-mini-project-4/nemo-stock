<script setup lang="ts">
import { computed } from 'vue'
import type { NodeTypeSchema } from '@/api/types'

const props = defineProps<{
  nodeTypes: NodeTypeSchema[]
}>()

const emit = defineEmits<{
  add: [schema: NodeTypeSchema]
}>()

const CATEGORY_LABELS: Record<string, string> = {
  scheduler: '스케줄러',
  data: '데이터',
  indicator: '지표·연산',
  ai: 'AI 해석',
  logic: '로직·제어',
  risk: '리스크',
  execution: '실행',
}

const grouped = computed(() => {
  const map = new Map<string, NodeTypeSchema[]>()
  for (const schema of props.nodeTypes) {
    if (!map.has(schema.category)) map.set(schema.category, [])
    map.get(schema.category)!.push(schema)
  }
  return map
})
</script>

<script lang="ts">
export const PALETTE_DRAG_MIME = 'application/x-nemo-node-type'
</script>

<template>
  <div class="palette">
    <h3>노드 팔레트</h3>
    <p class="palette-hint">클릭하거나 캔버스로 드래그해서 추가하세요.</p>
    <div v-for="[category, items] in grouped" :key="category" class="palette-group">
      <div class="palette-group-title">{{ CATEGORY_LABELS[category] ?? category }}</div>
      <button
        v-for="schema in items"
        :key="schema.type"
        class="palette-item"
        type="button"
        draggable="true"
        @click="emit('add', schema)"
        @dragstart="
          (event: DragEvent) => {
            event.dataTransfer?.setData(PALETTE_DRAG_MIME, schema.type)
            if (event.dataTransfer) event.dataTransfer.effectAllowed = 'copy'
          }
        "
      >
        {{ schema.display_name }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.palette {
  width: 190px;
  flex-shrink: 0;
  border-right: 1px solid var(--border);
  padding: 12px;
  overflow-y: auto;
}

.palette h3 {
  font-size: 13px;
  margin: 0 0 10px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.palette-hint {
  font-size: 11px;
  color: var(--text-muted);
  margin: -6px 0 10px;
}

.palette-group {
  margin-bottom: 14px;
}

.palette-group-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 6px;
}

.palette-item {
  display: block;
  width: 100%;
  text-align: left;
  padding: 7px 10px;
  margin-bottom: 4px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  font-size: 13px;
  cursor: grab;
}

.palette-item:hover {
  border-color: var(--accent);
  background: var(--bg);
}
</style>
