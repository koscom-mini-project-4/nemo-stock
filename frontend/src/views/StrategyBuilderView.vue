<script setup lang="ts">
import { computed, nextTick, onMounted, ref, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { Handle, Position, useVueFlow, VueFlow, type Edge as VFEdge, type Node as VFNode } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'

import {
  createWorkflow,
  fetchNodeTypes,
  fetchWorkflow,
  runWorkflow,
  updateWorkflow,
  validateWorkflow,
} from '@/api/services'
import type { NodeEventOut, NodeTypeSchema, ValidationResult, WorkflowGraph, WorkflowStatus } from '@/api/types'
import { flowElementsToGraph, graphToFlowElements, type FlowNodeData } from '@/utils/flowAdapter'
import { categoryColor } from '@/utils/categoryColors'
import { workflowStatusLabel } from '@/utils/labels'
import { useDraftStore } from '@/stores/draft'
import NodePalette, { PALETTE_DRAG_MIME } from '@/components/NodePalette.vue'
import PropertyPanel from '@/components/PropertyPanel.vue'
import ValidationPanel from '@/components/ValidationPanel.vue'
import DebugPanel from '@/components/DebugPanel.vue'
import TestRunModal from '@/components/TestRunModal.vue'
import ParamFields from '@/components/ParamFields.vue'
import ChatPanel from '@/components/ChatPanel.vue'

const props = defineProps<{ id?: string }>()

const router = useRouter()
const draftStore = useDraftStore()
const { fitView, screenToFlowCoordinate } = useVueFlow()

const workflowId = ref<string | null>(props.id ?? null)
const name = ref('이름 없는 전략')
const scheduleIntervalSec = ref(60)
const status = ref<WorkflowStatus>('draft')

const nodeTypes = ref<NodeTypeSchema[]>([])
const nodeTypesByKey = computed(() => new Map(nodeTypes.value.map((t) => [t.type, t])))

const flowNodes = ref([]) as Ref<VFNode<FlowNodeData>[]>
const flowEdges = ref([]) as Ref<VFEdge[]>
const selectedNodeId = ref<string | null>(null)
const selectedNode = computed<VFNode<FlowNodeData> | null>(
  () => flowNodes.value.find((n) => n.id === selectedNodeId.value) ?? null,
)
const selectedSchema = computed(() =>
  selectedNode.value ? nodeTypesByKey.value.get(selectedNode.value.data!.nodeType) : undefined,
)

const activeTab = ref<'properties' | 'validation' | 'debug' | 'chat'>('properties')
const validationResult = ref<ValidationResult | null>(null)
const validating = ref(false)
const saving = ref(false)
const savedMessage = ref('')

const testRunModalVisible = ref(false)
const debugEvents = ref<NodeEventOut[]>([])
const playingAnimation = ref(false)
const lastRunStatus = ref<string | null>(null)
const lastRunFinalSymbols = ref<Record<string, Record<string, unknown>> | null>(null)

let nodeSeq = 0
function nextNodeId() {
  nodeSeq += 1
  return `n${Date.now().toString(36)}${nodeSeq}`
}

function defaultParams(schema: NodeTypeSchema): Record<string, unknown> {
  const params: Record<string, unknown> = {}
  for (const spec of schema.param_schema) {
    params[spec.key] = spec.default
  }
  return params
}

async function load() {
  nodeTypes.value = await fetchNodeTypes()

  if (workflowId.value) {
    const wf = await fetchWorkflow(workflowId.value)
    name.value = wf.name
    scheduleIntervalSec.value = wf.schedule_interval_sec
    status.value = wf.status
    let graph = wf.graph

    // 백테스트 결과 화면의 AI 진단/수정 제안("전략 빌더에서 열기")에서 넘어온 draft가 이
    // 워크플로를 대상으로 하면, 저장된 그래프 대신 그 draft로 캔버스를 채운다(저장은 사용자가
    // 직접 검토 후 눌러야 함 — 미리보기 후 적용 원칙 유지).
    const draft = draftStore.pending
    if (draft && draft.targetWorkflowId === workflowId.value) {
      name.value = draft.name
      graph = draft.graph
      draftStore.consumeDraft()
    }

    const { nodes, edges } = graphToFlowElements(graph, nodeTypesByKey.value)
    flowNodes.value = nodes
    flowEdges.value = edges
    scheduleFitView()
    return
  }

  const draft = draftStore.consumeDraft()
  if (draft) {
    name.value = draft.name
    const { nodes, edges } = graphToFlowElements(draft.graph, nodeTypesByKey.value)
    flowNodes.value = nodes
    flowEdges.value = edges
    scheduleFitView()
    return
  }

  const schedulerSchema = nodeTypes.value.find((t) => t.category === 'scheduler')
  if (schedulerSchema) {
    addNode(schedulerSchema)
  }
}

function addNode(schema: NodeTypeSchema, position?: { x: number; y: number }) {
  const id = nextNodeId()
  const index = flowNodes.value.length
  flowNodes.value.push({
    id,
    type: 'workflow',
    position: position ?? { x: 40 + (index % 4) * 300, y: 40 + Math.floor(index / 4) * 200 },
    label: schema.display_name,
    targetPosition: Position.Left,
    sourcePosition: Position.Right,
    data: {
      nodeType: schema.type,
      category: schema.category,
      displayName: schema.display_name,
      params: defaultParams(schema),
      runStatus: null,
    },
  })
  scheduleFitView()
}

function onPaletteDragOver(event: DragEvent) {
  event.preventDefault()
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'
}

function onPaletteDrop(event: DragEvent) {
  event.preventDefault()
  const nodeType = event.dataTransfer?.getData(PALETTE_DRAG_MIME)
  if (!nodeType) return
  const schema = nodeTypesByKey.value.get(nodeType)
  if (!schema) return
  const position = screenToFlowCoordinate({ x: event.clientX, y: event.clientY })
  addNode(schema, position)
}

/**
 * fitView()는 Vue Flow가 노드 크기를 실제로 측정(ResizeObserver)한 뒤에 호출해야
 * 정확하다. nextTick만으로는 측정이 끝나기 전일 수 있어(특히 노드를 연속으로 빠르게
 * 추가할 때) 새 노드가 우측 패널 아래로 잘려 들어가는 문제가 있었다. 두 번의
 * requestAnimationFrame으로 측정 패스를 한 번 더 흘려보낸 뒤 fitView를 호출한다.
 */
function scheduleFitView() {
  nextTick(() => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        fitView({ padding: 0.2, duration: 200 })
      })
    })
  })
}

function onConnect(connection: { source: string; target: string }) {
  const exists = flowEdges.value.some((e) => e.source === connection.source && e.target === connection.target)
  if (exists) return
  flowEdges.value.push({
    id: `e-${connection.source}-${connection.target}-${Date.now()}`,
    source: connection.source,
    target: connection.target,
    markerEnd: 'arrowclosed',
  })
}

function onNodeClick(event: { node: VFNode<FlowNodeData> }) {
  selectedNodeId.value = event.node.id
  activeTab.value = 'properties'
}

function updateNodeParamById(nodeId: string, key: string, value: unknown) {
  const node = flowNodes.value.find((n) => n.id === nodeId)
  if (!node) return
  node.data!.params[key] = value
}

function updateParam(key: string, value: unknown) {
  if (!selectedNode.value) return
  updateNodeParamById(selectedNode.value.id, key, value)
}

function updateAllParams(params: Record<string, unknown>) {
  if (!selectedNode.value) return
  selectedNode.value.data!.params = params
}

function schemaFor(nodeType: string): NodeTypeSchema | undefined {
  return nodeTypesByKey.value.get(nodeType)
}

const currentGraph = computed<WorkflowGraph>(() => flowElementsToGraph(flowNodes.value, flowEdges.value))

const chatLastRun = computed(() =>
  lastRunStatus.value
    ? {
        status: lastRunStatus.value,
        events: debugEvents.value,
        final_symbols: lastRunFinalSymbols.value ?? {},
      }
    : null,
)

function applyChatGraph(payload: { name: string; graph: WorkflowGraph }) {
  if (payload.name) name.value = payload.name
  const { nodes, edges } = graphToFlowElements(payload.graph, nodeTypesByKey.value)
  flowNodes.value = nodes
  flowEdges.value = edges
  selectedNodeId.value = null
  scheduleFitView()
}

function deleteSelectedNode() {
  if (!selectedNode.value) return
  const id = selectedNode.value.id
  flowNodes.value = flowNodes.value.filter((n) => n.id !== id)
  flowEdges.value = flowEdges.value.filter((e) => e.source !== id && e.target !== id)
  selectedNodeId.value = null
}

async function save() {
  saving.value = true
  try {
    const graph = flowElementsToGraph(flowNodes.value, flowEdges.value)
    if (workflowId.value) {
      const wf = await updateWorkflow(workflowId.value, {
        name: name.value,
        graph,
        schedule_interval_sec: scheduleIntervalSec.value,
      })
      status.value = wf.status
    } else {
      const wf = await createWorkflow(name.value || '이름 없는 전략', graph, scheduleIntervalSec.value)
      workflowId.value = wf.id
      status.value = wf.status
      router.replace(`/strategies/${wf.id}`)
    }
    savedMessage.value = '저장되었습니다.'
    setTimeout(() => (savedMessage.value = ''), 2000)
  } finally {
    saving.value = false
  }
}

async function ensureSaved(): Promise<string> {
  if (!workflowId.value) {
    await save()
  }
  if (!workflowId.value) throw new Error('저장에 실패했습니다.')
  return workflowId.value
}

async function validate() {
  const id = await ensureSaved()
  validating.value = true
  activeTab.value = 'validation'
  try {
    validationResult.value = await validateWorkflow(id)
  } finally {
    validating.value = false
  }
}

async function toggleActivate() {
  try {
    const id = await ensureSaved()
    const next: WorkflowStatus = status.value === 'active' ? 'inactive' : 'active'
    const wf = await updateWorkflow(id, { status: next })
    status.value = wf.status
  } catch {
    alert('활성화에 실패했습니다. "검증" 탭에서 그래프 오류를 확인하세요.')
  }
}

async function openTestRun() {
  try {
    await ensureSaved()
  } catch {
    alert('전략을 저장하지 못해 테스트를 열 수 없습니다. 이름/그래프를 확인한 뒤 "저장" 버튼으로 다시 시도해주세요.')
    return
  }
  testRunModalVisible.value = true
}

const schedulerUniverse = computed(() => {
  const scheduler = flowNodes.value.find((n) => n.data?.category === 'scheduler')
  return (scheduler?.data?.params.universe as string) ?? ''
})

const overridesTemplate = computed(() => '{}')

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function animateEvents(events: NodeEventOut[]) {
  flowNodes.value.forEach((n) => {
    n.class = undefined
  })
  debugEvents.value = []
  for (const evt of events) {
    const node = flowNodes.value.find((n) => n.id === evt.node_id)
    if (node) {
      node.class = `flow-status status-${evt.status}`
    }
    debugEvents.value = [...debugEvents.value, evt]
    // eslint-disable-next-line no-await-in-loop
    await sleep(evt.status === 'running' ? 260 : 140)
  }
}

async function handleTestRun(payload: {
  universe: string[]
  overrides: Record<string, Record<string, Record<string, unknown>>>
}) {
  if (!workflowId.value) return
  testRunModalVisible.value = false
  playingAnimation.value = true
  activeTab.value = 'debug'
  try {
    const result = await runWorkflow(
      workflowId.value,
      payload.overrides,
      payload.universe.length ? payload.universe : undefined,
    )
    lastRunStatus.value = result.status
    lastRunFinalSymbols.value = result.final_symbols
    await animateEvents(result.events)
  } catch {
    alert('테스트 실행에 실패했습니다. "검증" 탭에서 그래프 오류를 확인하세요.')
  } finally {
    playingAnimation.value = false
  }
}

async function runNodeTest(nodeId: string) {
  // 선택된 노드의 최신 파라미터(예: 방금 고친 프롬프트)까지 반영해서 테스트하도록 먼저 저장한다.
  await save()
  if (!workflowId.value) return
  playingAnimation.value = true
  activeTab.value = 'debug'
  try {
    const result = await runWorkflow(workflowId.value, {}, undefined, nodeId)
    lastRunStatus.value = result.status
    lastRunFinalSymbols.value = result.final_symbols
    await animateEvents(result.events)
  } catch {
    alert('노드 테스트 실행에 실패했습니다. "검증" 탭에서 그래프 오류를 확인하세요.')
  } finally {
    playingAnimation.value = false
  }
}

async function goBacktest() {
  let id: string
  try {
    id = await ensureSaved()
  } catch {
    alert('전략을 저장하지 못해 백테스트를 열 수 없습니다. 이름/그래프를 확인한 뒤 "저장" 버튼으로 다시 시도해주세요.')
    return
  }
  router.push({ path: '/backtests/new', query: { workflow_id: id, universe: schedulerUniverse.value } })
}

onMounted(load)
</script>

<template>
  <div class="builder">
    <div class="toolbar">
      <RouterLink to="/" class="btn">← 대시보드</RouterLink>
      <input v-model="name" class="name-input" placeholder="전략 이름" />
      <label class="interval-input">
        주기(초)
        <input v-model.number="scheduleIntervalSec" type="number" min="1" />
      </label>
      <span :class="['badge', `badge-${status}`]">{{ workflowStatusLabel(status) }}</span>
      <span v-if="savedMessage" class="text-muted">{{ savedMessage }}</span>
      <div class="toolbar-spacer" />
      <button class="btn" :disabled="saving" @click="save">{{ saving ? '저장 중...' : '저장' }}</button>
      <button class="btn" @click="validate">검증</button>
      <button class="btn" @click="openTestRun">테스트 실행</button>
      <button class="btn" @click="goBacktest">백테스트</button>
      <button class="btn btn-primary" @click="toggleActivate">
        {{ status === 'active' ? '중지' : '활성화' }}
      </button>
    </div>

    <div class="builder-body">
      <NodePalette :node-types="nodeTypes" @add="addNode" />

      <div class="canvas" @dragover="onPaletteDragOver" @drop="onPaletteDrop">
        <VueFlow
          v-model:nodes="flowNodes"
          v-model:edges="flowEdges"
          fit-view-on-init
          :default-viewport="{ zoom: 0.9 }"
          @connect="onConnect"
          @node-click="onNodeClick"
        >
          <template #node-workflow="nodeProps">
            <div class="wf-node" :style="{ borderLeftColor: categoryColor(nodeProps.data.category) }">
              <Handle type="target" :position="Position.Left" />
              <div class="wf-node-header">
                <span
                  class="wf-node-dot"
                  :style="{ background: categoryColor(nodeProps.data.category) }"
                />
                <span class="wf-node-title">{{ nodeProps.data.displayName }}</span>
                <span class="wf-node-type mono">{{ nodeProps.data.nodeType }}</span>
              </div>
              <ParamFields
                v-if="schemaFor(nodeProps.data.nodeType)"
                compact
                :param-schema="schemaFor(nodeProps.data.nodeType)!.param_schema"
                :params="nodeProps.data.params"
                @update-param="(key, value) => updateNodeParamById(nodeProps.id, key, value)"
              />
              <Handle type="source" :position="Position.Right" />
            </div>
          </template>
          <Background pattern-color="var(--border)" :gap="16" />
          <Controls />
          <MiniMap />
        </VueFlow>
      </div>

      <div class="side-panel">
        <div class="tabs">
          <button :class="{ active: activeTab === 'properties' }" @click="activeTab = 'properties'">속성</button>
          <button :class="{ active: activeTab === 'validation' }" @click="activeTab = 'validation'">검증</button>
          <button :class="{ active: activeTab === 'debug' }" @click="activeTab = 'debug'">디버그</button>
          <button :class="{ active: activeTab === 'chat' }" @click="activeTab = 'chat'">AI 챗봇</button>
        </div>
        <div class="tab-content" :class="{ 'tab-content-chat': activeTab === 'chat' }">
          <PropertyPanel
            v-if="activeTab === 'properties'"
            :node="selectedNode"
            :schema="selectedSchema"
            @update-param="updateParam"
            @update-all-params="updateAllParams"
            @delete="deleteSelectedNode"
            @test-node="runNodeTest"
          />
          <ValidationPanel v-else-if="activeTab === 'validation'" :result="validationResult" :loading="validating" />
          <DebugPanel v-else-if="activeTab === 'debug'" :events="debugEvents" :playing="playingAnimation" />
          <ChatPanel
            v-else
            :name="name"
            :graph="currentGraph"
            :last-run="chatLastRun"
            :node-types="nodeTypes"
            @apply-graph="applyChatGraph"
          />
        </div>
      </div>
    </div>

    <TestRunModal
      :visible="testRunModalVisible"
      :default-universe="schedulerUniverse"
      :template-overrides="overridesTemplate"
      @close="testRunModalVisible = false"
      @run="handleTestRun"
    />
  </div>
</template>

<style scoped>
.builder {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--surface);
}

.name-input {
  width: 220px;
  font-weight: 600;
}

.interval-input {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-muted);
}

.interval-input input {
  width: 70px;
}

.toolbar-spacer {
  flex: 1;
}

.builder-body {
  display: flex;
  flex: 1;
  min-height: 0;
}

.canvas {
  flex: 1;
  min-width: 0;
  position: relative;
}

.canvas :deep(.vue-flow) {
  background: var(--bg);
}

.side-panel {
  width: 300px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--border);
}

.tabs {
  display: flex;
  border-bottom: 1px solid var(--border);
}

.tabs button {
  flex: 1;
  padding: 8px;
  border: none;
  background: var(--surface);
  color: var(--text-muted);
  font-size: 13px;
  border-bottom: 2px solid transparent;
}

.tabs button.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}

.tab-content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.tab-content.tab-content-chat {
  overflow-y: hidden;
  display: flex;
}

/* 캔버스 위 커스텀 노드 박스 — 파라미터를 노드 안에서 바로 보고 마우스로 수정할 수 있도록 표시한다. */
.wf-node {
  min-width: 190px;
  max-width: 240px;
  border: 1.5px solid var(--border);
  border-left-width: 4px;
  border-radius: 3px;
  background: var(--surface);
  box-shadow: 0 3px 10px rgba(17, 38, 75, 0.1);
  cursor: grab;
}

.wf-node-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 1px 6px;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  background: var(--bg);
  border-radius: 0 2px 0 0;
}

.wf-node-dot {
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.wf-node-title {
  font-size: 13px;
  font-weight: 600;
}

.wf-node-type {
  font-size: 10px;
  color: var(--text-muted);
}

.wf-node :deep(.param-fields) {
  padding: 8px 10px;
}

.wf-node :deep(.param-fields.compact:empty),
.wf-node :deep(.no-params) {
  padding: 6px 10px;
  margin: 0;
}
</style>

<style>
/* Vue Flow가 내부적으로 렌더링하는 노드 DOM에는 scoped 속성이 적용되지 않으므로 전역 스타일로 정의한다. */
.flow-status {
  border-radius: 3px;
  transition: box-shadow 0.2s, border-color 0.2s;
}

.flow-status.status-running {
  border-color: var(--running) !important;
  box-shadow: 0 0 0 3px rgba(234, 179, 8, 0.35);
  animation: nemo-pulse 0.7s ease-in-out infinite alternate;
}

.flow-status.status-success {
  border-color: var(--success) !important;
  box-shadow: 0 0 0 2px rgba(22, 163, 74, 0.25);
}

.flow-status.status-error {
  border-color: var(--danger) !important;
  box-shadow: 0 0 0 2px rgba(220, 38, 38, 0.3);
}

.flow-status.status-skipped {
  opacity: 0.5;
}

@keyframes nemo-pulse {
  from {
    box-shadow: 0 0 0 2px rgba(234, 179, 8, 0.25);
  }
  to {
    box-shadow: 0 0 0 6px rgba(234, 179, 8, 0.45);
  }
}
</style>
