<script setup lang="ts">
import { computed } from 'vue'
import type { NodeTypeSchema } from '@/api/types'
import { categoryColor } from '@/utils/categoryColors'

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

interface SubGroup {
  subcategory: string
  items: NodeTypeSchema[]
}

const grouped = computed(() => {
  const map = new Map<string, NodeTypeSchema[]>()
  for (const schema of props.nodeTypes) {
    if (!map.has(schema.category)) map.set(schema.category, [])
    map.get(schema.category)!.push(schema)
  }
  // 각 카테고리 안에서 subcategory(분류)로 한 번 더 묶는다. subcategory가 없으면 단일 그룹.
  const result: [string, SubGroup[]][] = []
  for (const [category, items] of map) {
    const subMap = new Map<string, NodeTypeSchema[]>()
    for (const schema of items) {
      const sub = schema.subcategory ?? ''
      if (!subMap.has(sub)) subMap.set(sub, [])
      subMap.get(sub)!.push(schema)
    }
    const subGroups: SubGroup[] = [...subMap.entries()].map(([subcategory, subItems]) => ({
      subcategory,
      items: subItems,
    }))
    result.push([category, subGroups])
  }
  return result
})

function itemTitle(schema: NodeTypeSchema): string {
  return schema.example ? `${schema.description}\n예: ${schema.example}` : schema.description
}
</script>

<script lang="ts">
export const PALETTE_DRAG_MIME = 'application/x-nemo-node-type'
</script>

<template>
  <div class="palette">
    <h3>노드 팔레트</h3>
    <p class="palette-hint">클릭하거나 캔버스로 드래그해서 추가하세요.</p>
    <div v-for="[category, subGroups] in grouped" :key="category" class="palette-group">
      <div class="palette-group-title">{{ CATEGORY_LABELS[category] ?? category }}</div>
      <template v-for="sub in subGroups" :key="category + ':' + sub.subcategory">
        <div v-if="sub.subcategory" class="palette-subtitle">{{ sub.subcategory }}</div>
        <button
          v-for="schema in sub.items"
          :key="schema.type"
          class="palette-item"
          type="button"
          draggable="true"
          :title="itemTitle(schema)"
          :style="{ borderLeftColor: categoryColor(schema.category) }"
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
      </template>
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
  background: var(--surface);
  box-shadow: 2px 0 10px rgba(24, 49, 88, 0.04);
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

.palette-subtitle {
  font-size: 10.5px;
  font-weight: 600;
  color: var(--accent);
  margin: 6px 0 3px;
  padding-left: 2px;
}

.palette-item {
  display: block;
  width: 100%;
  text-align: left;
  padding: 7px 10px;
  margin-bottom: 4px;
  border-radius: 4px;
  border: 1px solid var(--border);
  border-left: 3px solid var(--border);
  background: var(--surface);
  color: var(--text);
  font-size: 13px;
  cursor: grab;
  transition: background 0.15s, box-shadow 0.15s;
}

.palette-item:hover {
  background: var(--bg);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}
</style>
