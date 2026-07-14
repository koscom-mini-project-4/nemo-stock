<script setup lang="ts">
import type { Node as VFNode } from '@vue-flow/core'
import type { NodeTypeSchema } from '@/api/types'
import type { FlowNodeData } from '@/utils/flowAdapter'

const props = defineProps<{
  node: VFNode<FlowNodeData> | null
  schema: NodeTypeSchema | undefined
}>()

const emit = defineEmits<{
  'update-param': [key: string, value: unknown]
  delete: []
}>()

function onInput(key: string, event: Event) {
  const target = event.target as HTMLInputElement
  emit('update-param', key, target.value)
}

function onNumberInput(key: string, event: Event) {
  const target = event.target as HTMLInputElement
  emit('update-param', key, target.value === '' ? '' : Number(target.value))
}

function onCheckbox(key: string, event: Event) {
  const target = event.target as HTMLInputElement
  emit('update-param', key, target.checked)
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

      <div v-if="!schema" class="text-muted">알 수 없는 노드 타입입니다.</div>
      <div v-else-if="schema.param_schema.length === 0" class="text-muted">파라미터가 없는 노드입니다.</div>
      <div v-else class="param-form">
        <label v-for="spec in schema.param_schema" :key="spec.key" class="param-field">
          <span>{{ spec.label }}<span v-if="spec.required" class="required">*</span></span>

          <select
            v-if="spec.type === 'select'"
            :value="(node.data?.params[spec.key] as string) ?? spec.default"
            @change="onInput(spec.key, $event)"
          >
            <option v-for="opt in spec.options ?? []" :key="opt" :value="opt">{{ opt }}</option>
          </select>

          <input
            v-else-if="spec.type === 'boolean'"
            type="checkbox"
            :checked="Boolean(node.data?.params[spec.key] ?? spec.default)"
            @change="onCheckbox(spec.key, $event)"
          />

          <input
            v-else-if="spec.type === 'number'"
            type="number"
            :value="(node.data?.params[spec.key] as number) ?? spec.default"
            @input="onNumberInput(spec.key, $event)"
          />

          <textarea
            v-else-if="spec.type === 'expression'"
            rows="2"
            :value="(node.data?.params[spec.key] as string) ?? spec.default"
            @input="onInput(spec.key, $event)"
          />

          <input
            v-else
            type="text"
            :value="(node.data?.params[spec.key] as string) ?? spec.default"
            @input="onInput(spec.key, $event)"
          />
        </label>
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
  margin-bottom: 14px;
  gap: 8px;
}

.param-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.param-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
}

.required {
  color: var(--danger);
  margin-left: 2px;
}
</style>
