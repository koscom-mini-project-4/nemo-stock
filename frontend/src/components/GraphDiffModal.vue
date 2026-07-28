<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { NodeTypeSchema, WorkflowGraph } from '@/api/types'
import { diffGraphs } from '@/utils/graphDiff'

const props = defineProps<{
  visible: boolean
  beforeName: string
  afterName: string
  before: WorkflowGraph
  after: WorkflowGraph
  nodeTypes: NodeTypeSchema[]
  refining: boolean
  refineError: string
}>()

const emit = defineEmits<{
  dismiss: []
  confirm: []
  cancel: []
  refine: [instruction: string]
}>()

const refineInput = ref('')

watch(
  () => props.visible,
  (visible) => {
    if (visible) refineInput.value = ''
  },
)

const nodeTypesByKey = computed(() => new Map(props.nodeTypes.map((t) => [t.type, t])))

function nodeLabel(type: string): string {
  return nodeTypesByKey.value.get(type)?.display_name ?? type
}

function paramLabel(type: string, key: string): string {
  const schema = nodeTypesByKey.value.get(type)
  return schema?.param_schema.find((p) => p.key === key)?.label ?? key
}

function fmt(value: unknown): string {
  if (value === undefined) return '(없음)'
  if (value === null) return 'null'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

const diff = computed(() => diffGraphs(props.before, props.after))
const nameChanged = computed(() => props.beforeName !== props.afterName)
const hasChanges = computed(() => diff.value.nodeChanges.length > 0 || diff.value.edgeChanges.length > 0 || nameChanged.value)

function submitRefine() {
  const text = refineInput.value.trim()
  if (!text || props.refining) return
  emit('refine', text)
  refineInput.value = ''
}
</script>

<template>
  <div v-if="visible" class="modal-backdrop" @click.self="emit('dismiss')">
    <div class="card modal">
      <div class="modal-header">
        <h2>AI 변경 제안 검토</h2>
        <button class="icon-btn" type="button" title="닫기(제안 유지)" @click="emit('dismiss')">×</button>
      </div>

      <p v-if="nameChanged" class="name-diff">
        전략 이름: <span class="before">{{ beforeName }}</span> → <span class="after">{{ afterName }}</span>
      </p>

      <div class="diff-body">
        <p v-if="!hasChanges" class="text-muted">실질적인 변경 사항이 없습니다.</p>

        <template v-else>
          <div v-for="entry in diff.nodeChanges" :key="entry.id" :class="['diff-entry', `diff-${entry.status}`]">
            <div class="diff-entry-head">
              <span class="diff-badge" :class="`badge-${entry.status}`">
                {{ entry.status === 'added' ? '추가' : entry.status === 'removed' ? '삭제' : '변경' }}
              </span>
              <span class="diff-node-label">
                {{ nodeLabel((entry.after ?? entry.before)!.type) }}
                <span class="text-muted mono">({{ entry.id }})</span>
              </span>
            </div>
            <div v-if="entry.typeChanged" class="diff-param-row">
              타입: <span class="before">{{ entry.before!.type }}</span> → <span class="after">{{ entry.after!.type }}</span>
            </div>
            <div v-for="pd in entry.paramDiffs" :key="pd.key" class="diff-param-row">
              {{ paramLabel((entry.after ?? entry.before)!.type, pd.key) }}:
              <span class="before">{{ fmt(pd.before) }}</span> → <span class="after">{{ fmt(pd.after) }}</span>
            </div>
          </div>

          <div v-if="diff.edgeChanges.length > 0" class="edge-diff">
            <div v-for="e in diff.edgeChanges" :key="e.key" :class="['diff-entry-inline', `diff-${e.status}`]">
              <span class="diff-badge" :class="`badge-${e.status}`">{{ e.status === 'added' ? '추가' : '삭제' }}</span>
              <span class="mono">{{ e.edge.from }} → {{ e.edge.to }}<template v-if="e.edge.branch">[{{ e.edge.branch }}]</template></span>
            </div>
          </div>

          <p v-if="diff.unchangedNodeCount > 0" class="text-muted unchanged-hint">
            변경 없는 노드 {{ diff.unchangedNodeCount }}개는 생략했습니다.
          </p>
        </template>
      </div>

      <p v-if="refineError" class="error">{{ refineError }}</p>

      <div class="refine-row">
        <input
          v-model="refineInput"
          type="text"
          placeholder="이 제안을 더 고쳐서 다시 제시해줘 (예: 손절 라인도 3%로 낮춰줘)"
          :disabled="refining"
          @keydown.enter="submitRefine"
        />
        <button class="btn" type="button" :disabled="refining || !refineInput.trim()" @click="submitRefine">
          {{ refining ? '반영 중...' : '다시 수정 요청' }}
        </button>
      </div>

      <div class="modal-actions">
        <button class="btn" type="button" :disabled="refining" @click="emit('cancel')">확정 취소</button>
        <button class="btn btn-primary" type="button" :disabled="refining" @click="emit('confirm')">확정</button>
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
  z-index: 60;
}

.modal {
  width: 620px;
  max-width: 94vw;
  max-height: 84vh;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.modal-header h2 {
  margin: 0;
  font-size: 17px;
}

.icon-btn {
  background: none;
  border: none;
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  color: var(--text-muted);
  padding: 2px 6px;
}

.name-diff {
  margin: 0;
  font-size: 13px;
}

.diff-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 10px;
}

.diff-entry {
  border-left: 3px solid var(--border);
  padding: 4px 0 4px 8px;
  font-size: 12.5px;
}

.diff-added {
  border-left-color: var(--accent);
}

.diff-removed {
  border-left-color: var(--danger);
}

.diff-changed {
  border-left-color: #d9a441;
}

.diff-entry-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 2px;
}

.diff-node-label {
  font-weight: 600;
}

.diff-badge {
  font-size: 11px;
  border-radius: 4px;
  padding: 1px 6px;
  color: white;
}

.badge-added {
  background: var(--accent);
}

.badge-removed {
  background: var(--danger);
}

.badge-changed {
  background: #d9a441;
}

.diff-param-row {
  padding-left: 4px;
  font-size: 12px;
  color: var(--text-muted);
}

.diff-param-row .before {
  color: var(--danger);
  text-decoration: line-through;
}

.diff-param-row .after,
.name-diff .after {
  color: var(--accent);
  font-weight: 600;
}

.name-diff .before {
  color: var(--text-muted);
  text-decoration: line-through;
}

.edge-diff {
  border-top: 1px dashed var(--border);
  padding-top: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.diff-entry-inline {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.unchanged-hint {
  font-size: 11.5px;
  margin: 0;
}

.error {
  color: var(--danger);
  font-size: 12.5px;
  margin: 0;
}

.refine-row {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

.refine-row input {
  flex: 1;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  flex-shrink: 0;
}
</style>
