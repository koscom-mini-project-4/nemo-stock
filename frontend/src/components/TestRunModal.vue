<script setup lang="ts">
import { ref, watch } from 'vue'
import SymbolAutocomplete from '@/components/SymbolAutocomplete.vue'

const props = defineProps<{
  visible: boolean
  defaultUniverse: string
  templateOverrides: string
}>()

const emit = defineEmits<{
  close: []
  run: [payload: { universe: string[]; overrides: Record<string, Record<string, Record<string, unknown>>> }]
}>()

const universeText = ref(props.defaultUniverse)
const overridesText = ref(props.templateOverrides)
const jsonError = ref('')

watch(
  () => props.visible,
  (visible) => {
    if (visible) {
      universeText.value = props.defaultUniverse
      overridesText.value = props.templateOverrides
      jsonError.value = ''
    }
  },
)

function submit() {
  let overrides: Record<string, Record<string, Record<string, unknown>>> = {}
  const trimmed = overridesText.value.trim()
  if (trimmed) {
    try {
      overrides = JSON.parse(trimmed)
    } catch {
      jsonError.value = 'overrides가 올바른 JSON 형식이 아닙니다.'
      return
    }
  }
  jsonError.value = ''
  const universe = universeText.value
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
  emit('run', { universe, overrides })
}
</script>

<template>
  <div v-if="visible" class="modal-backdrop" @click.self="emit('close')">
    <div class="card modal">
      <h2>테스트 실행</h2>
      <p class="text-muted">
        임의의 종목/값으로 워크플로를 즉시 실행해 노드별 결과를 확인합니다. 데이터 노드의 출력을
        직접 지정하려면 overrides에 <code>{"노드id": {"종목코드": {"필드": 값}}}</code> 형식으로 입력하세요.
      </p>

      <label>
        대상 종목코드 (콤마 구분)
        <SymbolAutocomplete v-model="universeText" />
      </label>

      <label>
        overrides (JSON, 선택)
        <textarea v-model="overridesText" rows="6" placeholder='{"n2": {"005930": {"price": 71000}}}' />
      </label>

      <p v-if="jsonError" class="error">{{ jsonError }}</p>

      <div class="modal-actions">
        <button class="btn" type="button" @click="emit('close')">취소</button>
        <button class="btn btn-primary" type="button" @click="submit">실행</button>
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
  z-index: 50;
}

.modal {
  width: 480px;
  max-width: 92vw;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.modal h2 {
  margin: 0;
  font-size: 17px;
}

label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
  color: var(--text-muted);
}

textarea {
  font-family: ui-monospace, monospace;
  font-size: 12.5px;
}

.error {
  color: var(--danger);
  font-size: 13px;
  margin: 0;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}
</style>
