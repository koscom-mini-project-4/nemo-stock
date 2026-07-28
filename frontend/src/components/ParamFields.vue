<script setup lang="ts">
import { computed } from 'vue'
import type { NodeParamSchema } from '@/api/types'

const props = defineProps<{
  paramSchema: NodeParamSchema[]
  params: Record<string, unknown>
  compact?: boolean
}>()

const emit = defineEmits<{
  'update-param': [key: string, value: unknown]
}>()

const GROUP_LABELS: Record<string, string> = {
  calc: '계산용 파라미터',
  condition: '매매 조건',
}

// show_if 조건(다른 파라미터 값에 의존)이 충족된 필드만 노출한다.
function isVisible(spec: NodeParamSchema): boolean {
  if (!spec.show_if) return true
  const current = props.params[spec.show_if.param] ?? ''
  return String(current) === spec.show_if.equals
}

// select의 옵션 라벨(프리셋 사람이 읽는 라벨)을 반환한다.
function optionLabel(spec: NodeParamSchema, idx: number, value: string): string {
  return spec.option_labels?.[idx] ?? value
}

// group이 지정된 파라미터가 하나라도 있으면 그룹 헤더로 구획을 나눠 보여준다.
const groups = computed(() => {
  const visible = props.paramSchema.filter(isVisible)
  const hasGroups = visible.some((s) => s.group)
  if (!hasGroups) return [{ key: '', label: '', items: visible }]
  const order = ['calc', 'condition', '']
  const map = new Map<string, NodeParamSchema[]>()
  for (const spec of visible) {
    const g = spec.group ?? ''
    if (!map.has(g)) map.set(g, [])
    map.get(g)!.push(spec)
  }
  return order
    .filter((g) => map.has(g))
    .map((g) => ({ key: g, label: GROUP_LABELS[g] ?? '', items: map.get(g)! }))
})

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
    <div v-for="grp in groups" :key="grp.key || 'default'" class="param-group">
      <div v-if="grp.label" class="param-group-title">{{ grp.label }}</div>
      <label
        v-for="spec in grp.items"
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
          <option v-for="(opt, i) in spec.options ?? []" :key="opt" :value="opt">
            {{ optionLabel(spec, i, opt) }}
          </option>
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

        <span v-if="spec.hint && !compact" class="param-hint">{{ spec.hint }}</span>
      </label>
    </div>
  </div>
</template>

<style scoped>
.param-fields {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.param-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.param-group + .param-group {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed var(--border);
}

.param-group-title {
  font-size: 11px;
  font-weight: 700;
  color: var(--accent);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.param-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
}

.param-hint {
  font-size: 11px;
  color: var(--text-muted);
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

.param-fields.compact .param-group {
  gap: 5px;
}

.param-fields.compact .param-group + .param-group {
  margin-top: 6px;
  padding-top: 5px;
}

.param-fields.compact .param-group-title {
  font-size: 9px;
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
