<script setup lang="ts">
import { ref, watch } from 'vue'
import type { Node as VFNode } from '@vue-flow/core'
import type { NodeTypeSchema } from '@/api/types'
import type { FlowNodeData } from '@/utils/flowAdapter'
import ParamFields from '@/components/ParamFields.vue'

const props = defineProps<{
  node: VFNode<FlowNodeData> | null
  schema: NodeTypeSchema | undefined
}>()

const emit = defineEmits<{
  'update-param': [key: string, value: unknown]
  'update-all-params': [params: Record<string, unknown>]
  delete: []
}>()

const mode = ref<'form' | 'code'>('form')
const codeText = ref('{}')
const codeError = ref('')

function syncCodeFromNode() {
  codeText.value = JSON.stringify(props.node?.data?.params ?? {}, null, 2)
  codeError.value = ''
}

watch(
  () => props.node?.id,
  () => syncCodeFromNode(),
)

function switchMode(next: 'form' | 'code') {
  if (next === 'code') syncCodeFromNode()
  mode.value = next
}

function applyCode() {
  try {
    const parsed = JSON.parse(codeText.value)
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      codeError.value = 'JSON 객체({...}) 형식이어야 합니다.'
      return
    }
    emit('update-all-params', parsed as Record<string, unknown>)
    codeError.value = ''
  } catch {
    codeError.value = '올바른 JSON 형식이 아닙니다.'
  }
}
</script>

<template>
  <div class="property-panel">
    <template v-if="node">
      <div class="panel-head">
        <div>
          <strong>{{ node.data?.displayName }}</strong>
          <div class="text-muted mono">{{ node.id }} · {{ node.data?.nodeType }}</div>
        </div>
        <button class="btn btn-danger" type="button" @click="emit('delete')">삭제</button>
      </div>

      <div class="mode-tabs">
        <button type="button" :class="{ active: mode === 'form' }" @click="switchMode('form')">폼</button>
        <button type="button" :class="{ active: mode === 'code' }" @click="switchMode('code')">코드(JSON)</button>
      </div>

      <div v-if="!schema" class="text-muted">알 수 없는 노드 타입입니다.</div>
      <p v-else-if="schema.description" class="text-muted node-description">{{ schema.description }}</p>
      <ParamFields
        v-else-if="mode === 'form'"
        :param-schema="schema.param_schema"
        :params="node.data?.params ?? {}"
        @update-param="(key, value) => emit('update-param', key, value)"
      />
      <div v-else class="code-editor">
        <textarea v-model="codeText" rows="12" class="mono" spellcheck="false" />
        <div class="code-actions">
          <button class="btn btn-primary" type="button" @click="applyCode">적용</button>
          <span v-if="codeError" class="error">{{ codeError }}</span>
        </div>
      </div>
    </template>
    <p v-else class="text-muted">캔버스에서 노드를 선택하면 속성을 편집할 수 있습니다.</p>
  </div>
</template>

<style scoped>
.property-panel {
  width: 280px;
  flex-shrink: 0;
  border-left: 1px solid var(--border);
  padding: 12px;
  overflow-y: auto;
}

.panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 10px;
  gap: 8px;
}

.mode-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 2px;
}

.mode-tabs button {
  flex: 1;
  border: none;
  background: transparent;
  color: var(--text-muted);
  font-size: 12.5px;
  padding: 5px 0;
  border-radius: 4px;
}

.mode-tabs button.active {
  background: var(--accent);
  color: white;
}

.code-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.code-editor textarea {
  font-size: 12px;
  line-height: 1.4;
}

.code-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.code-actions .error {
  color: var(--danger);
  font-size: 12px;
}

.node-description {
  font-size: 12px;
  line-height: 1.5;
  margin: 0 0 12px;
}
</style>
