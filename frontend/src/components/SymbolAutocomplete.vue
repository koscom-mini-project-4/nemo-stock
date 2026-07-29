<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useSymbolMasterStore } from '@/stores/symbolMaster'

// 콤마로 구분된 종목코드 목록(v-model)을 편집하는 입력창에 자동완성을 붙인다. 현재 입력
// 중인 마지막 토큰(콤마 뒤)만 종목코드/한글명 부분일치로 검색해 드롭다운으로 보여주고,
// 선택하면 그 토큰을 종목코드로 치환한다 — symbolMaster 스토어의 캐시(§0-10)를 그대로
// 클라이언트에서 필터링하므로 타이핑마다 API를 호출하지 않는다.
const props = withDefaults(defineProps<{ modelValue: string; placeholder?: string }>(), {
  placeholder: '005930,000660 또는 삼성전자,SK하이닉스',
})
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const store = useSymbolMasterStore()
onMounted(() => store.ensureLoaded())

const inputEl = ref<HTMLInputElement | null>(null)
const open = ref(false)
const highlighted = ref(0)

const currentToken = computed(() => {
  const parts = props.modelValue.split(',')
  return parts[parts.length - 1].trim()
})

const suggestions = computed(() => (open.value ? store.search(currentToken.value) : []))

function onInput(e: Event) {
  emit('update:modelValue', (e.target as HTMLInputElement).value)
  open.value = true
  highlighted.value = 0
}

function applySuggestion(s: { symbol: string; name: string }) {
  // 마지막(입력 중이던) 토큰을 선택한 종목코드로 치환하고, 다음 종목을 이어 입력할 수 있도록
  // 콤마를 붙여둔다.
  const parts = props.modelValue
    .split(',')
    .slice(0, -1)
    .map((p) => p.trim())
    .filter(Boolean)
  parts.push(s.symbol)
  emit('update:modelValue', `${parts.join(', ')}, `)
  open.value = false
  inputEl.value?.focus()
}

function onKeydown(e: KeyboardEvent) {
  if (!open.value || suggestions.value.length === 0) return
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    highlighted.value = (highlighted.value + 1) % suggestions.value.length
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    highlighted.value = (highlighted.value - 1 + suggestions.value.length) % suggestions.value.length
  } else if (e.key === 'Enter' || e.key === 'Tab') {
    e.preventDefault()
    applySuggestion(suggestions.value[highlighted.value])
  } else if (e.key === 'Escape') {
    open.value = false
  }
}

function onBlur() {
  // 클릭 선택이 처리될 시간을 준 뒤 닫는다(mousedown보다 늦게 실행되면 클릭이 씹힌다).
  setTimeout(() => (open.value = false), 150)
}
</script>

<template>
  <div class="symbol-autocomplete">
    <input
      ref="inputEl"
      type="text"
      :value="modelValue"
      :placeholder="placeholder"
      @input="onInput"
      @keydown="onKeydown"
      @focus="open = true"
      @blur="onBlur"
    />
    <ul v-if="open && suggestions.length" class="suggestions">
      <li
        v-for="(s, i) in suggestions"
        :key="s.symbol"
        :class="{ active: i === highlighted }"
        @mousedown.prevent="applySuggestion(s)"
      >
        <span class="mono">{{ s.symbol }}</span>
        <span class="name">{{ s.name }}</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.symbol-autocomplete {
  position: relative;
}

.suggestions {
  position: absolute;
  z-index: 20;
  top: calc(100% + 2px);
  left: 0;
  right: 0;
  max-height: 220px;
  overflow-y: auto;
  margin: 0;
  padding: 4px;
  list-style: none;
  background: var(--surface, #fff);
  border: 1px solid var(--border);
  border-radius: 4px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
}

.suggestions li {
  display: flex;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}

.suggestions li.active,
.suggestions li:hover {
  background: var(--hover-bg, rgba(0, 0, 0, 0.06));
}

.suggestions .mono {
  font-family: ui-monospace, monospace;
  color: var(--text-muted);
}
</style>
