<script setup lang="ts">
import type { NodeParamSchema } from '@/api/types'

defineProps<{
  paramSchema: NodeParamSchema[]
  params: Record<string, unknown>
  compact?: boolean
}>()

const emit = defineEmits<{
  'update-param': [key: string, value: unknown]
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
  <div class="param-fields" :class="{ compact }">
    <p v-if="paramSchema.length === 0" class="text-muted no-params">파라미터 없음</p>
    <label
      v-for="spec in paramSchema"
      :key="spec.key"
      class="param-field"
      :class="{ 'is-expression': spec.type === 'expression' }"
    >
      <span class="param-label">{{ spec.label }}<span v-if="spec.required" class="required">*</span></span>

      <select
        v-if="spec.type === 'select'"
        class="nodrag nopan"
        :value="(params[spec.key] as string) ?? spec.default"
        @mousedown.stop
        @change="onInput(spec.key, $event)"
      >
        <option v-for="opt in spec.options ?? []" :key="opt" :value="opt">{{ opt }}</option>
      </select>

      <input
        v-else-if="spec.type === 'boolean'"
        type="checkbox"
        class="nodrag nopan"
        :checked="Boolean(params[spec.key] ?? spec.default)"
        @mousedown.stop
        @change="onCheckbox(spec.key, $event)"
      />

      <input
        v-else-if="spec.type === 'number'"
        type="number"
        class="nodrag nopan"
        :value="(params[spec.key] as number) ?? spec.default"
        @mousedown.stop
        @input="onNumberInput(spec.key, $event)"
      />

      <textarea
        v-else-if="spec.type === 'expression'"
        class="nodrag nopan mono"
        :rows="compact ? 1 : 2"
        :value="(params[spec.key] as string) ?? spec.default"
        @mousedown.stop
        @input="onInput(spec.key, $event)"
      />

      <input
        v-else
        type="text"
        class="nodrag nopan"
        :value="(params[spec.key] as string) ?? spec.default"
        @mousedown.stop
        @input="onInput(spec.key, $event)"
      />
    </label>
  </div>
</template>

<style scoped>
.param-fields {
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

.no-params {
  margin: 0;
}

/* 캔버스 노드 안에 인라인으로 렌더링될 때의 압축 스타일 */
.param-fields.compact {
  gap: 5px;
}

.param-fields.compact .param-field {
  gap: 2px;
  font-size: 11px;
}

.param-fields.compact .param-label {
  color: var(--text-muted);
  font-size: 10.5px;
}

.param-fields.compact input,
.param-fields.compact select,
.param-fields.compact textarea {
  padding: 3px 6px;
  font-size: 11.5px;
  border-radius: 4px;
}

.param-fields.compact input[type='checkbox'] {
  width: auto;
  align-self: flex-start;
}

.param-fields.compact textarea {
  resize: none;
}

.param-field.is-expression textarea {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

.param-fields.compact .param-field.is-expression {
  background: color-mix(in srgb, var(--accent) 8%, transparent);
  border-radius: 5px;
  padding: 4px 6px;
}

.param-fields.compact .param-field.is-expression .param-label {
  color: var(--accent);
  font-weight: 600;
}
</style>
