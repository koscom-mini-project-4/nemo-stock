<script setup lang="ts">
/**
 * 워크플로 그래프를 읽기 전용으로 그려 보여주는 미리보기 캔버스. AI 초안처럼 아직 저장되지
 * 않은 그래프를 텍스트 목록 대신 실제 노드/간선 배치로 보여줄 때 쓴다(캔버스 조작은
 * StrategyBuilderView.vue에서만 하고, 여기서는 드래그/연결/선택을 모두 막는다).
 */
import { computed, nextTick, watch } from 'vue'
import { Handle, Position, useVueFlow, VueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'

import type { NodeTypeSchema, WorkflowGraph } from '@/api/types'
import { graphToFlowElements } from '@/utils/flowAdapter'
import { categoryColor } from '@/utils/categoryColors'

const props = withDefaults(
  defineProps<{
    graph: WorkflowGraph
    nodeTypes?: NodeTypeSchema[]
    height?: string
  }>(),
  { nodeTypes: () => [], height: '320px' },
)

const { fitView } = useVueFlow()

const nodeTypesByKey = computed(() => new Map(props.nodeTypes.map((t) => [t.type, t])))
const flowElements = computed(() => graphToFlowElements(props.graph, nodeTypesByKey.value))
const flowNodes = computed(() => flowElements.value.nodes)
const flowEdges = computed(() => flowElements.value.edges)

function scheduleFitView() {
  nextTick(() => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        fitView({ padding: 0.2, duration: 200 })
      })
    })
  })
}

watch(() => props.graph, scheduleFitView, { immediate: true })
</script>

<template>
  <div class="preview-canvas" :style="{ height }">
    <VueFlow
      :nodes="flowNodes"
      :edges="flowEdges"
      fit-view-on-init
      :nodes-draggable="false"
      :nodes-connectable="false"
      :elements-selectable="false"
      :min-zoom="0.2"
    >
      <template #node-workflow="nodeProps">
        <div class="pv-node" :style="{ borderLeftColor: categoryColor(nodeProps.data.category) }">
          <Handle type="target" :position="Position.Left" />
          <span class="pv-node-dot" :style="{ background: categoryColor(nodeProps.data.category) }" />
          <span class="pv-node-title">{{ nodeProps.data.displayName }}</span>
          <span class="pv-node-type mono">{{ nodeProps.data.nodeType }}</span>
          <Handle type="source" :position="Position.Right" />
        </div>
      </template>
      <Background pattern-color="var(--border)" :gap="16" />
    </VueFlow>
  </div>
</template>

<style scoped>
.preview-canvas {
  position: relative;
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 4px;
  overflow: hidden;
  background: var(--bg);
}

.preview-canvas :deep(.vue-flow) {
  background: var(--bg);
}

.pv-node {
  min-width: 150px;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 10px;
  border: 1.5px solid var(--border);
  border-left-width: 4px;
  border-radius: 3px;
  background: var(--surface);
  box-shadow: 0 2px 8px rgba(17, 38, 75, 0.08);
  cursor: default;
}

.pv-node-dot {
  flex-shrink: 0;
  width: 7px;
  height: 7px;
  border-radius: 50%;
}

.pv-node-title {
  font-size: 12.5px;
  font-weight: 600;
}

.pv-node-type {
  font-size: 10px;
  color: var(--text-muted);
}
</style>
