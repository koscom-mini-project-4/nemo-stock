<script setup lang="ts">
import { ref, watch } from 'vue'
import SymbolAutocomplete from '@/components/SymbolAutocomplete.vue'

// 보유 포지션 수동 추가/수정 팝업. mode="create"면 종목코드를 직접 입력(자동완성)하고,
// mode="edit"이면 symbol이 고정된 채 수량/평단가만 바꾼다.
const props = defineProps<{
  visible: boolean
  mode: 'create' | 'edit'
  symbol?: string
  qty?: number
  avgPrice?: number
}>()

const emit = defineEmits<{
  close: []
  save: [payload: { symbol: string; qty: number; avgPrice: number }]
}>()

const symbolText = ref('')
const qty = ref(1)
const avgPrice = ref(0)
const errorMessage = ref('')

watch(
  () => props.visible,
  (visible) => {
    if (!visible) return
    symbolText.value = props.symbol ?? ''
    qty.value = props.qty ?? 1
    avgPrice.value = props.avgPrice ?? 0
    errorMessage.value = ''
  },
)

function submit() {
  const symbol = (props.mode === 'edit' ? props.symbol : symbolText.value.split(',')[0])?.trim()
  if (!symbol) {
    errorMessage.value = '종목코드를 입력하세요.'
    return
  }
  if (qty.value <= 0) {
    errorMessage.value = '수량은 1 이상이어야 합니다.'
    return
  }
  emit('save', { symbol, qty: qty.value, avgPrice: avgPrice.value })
}
</script>

<template>
  <div v-if="visible" class="modal-backdrop" @click.self="emit('close')">
    <div class="card modal">
      <h2>{{ mode === 'create' ? '종목 직접 추가' : `${symbol} 포지션 수정` }}</h2>

      <label v-if="mode === 'create'">
        종목코드
        <SymbolAutocomplete v-model="symbolText" placeholder="005930 또는 삼성전자" />
      </label>
      <label v-else>
        종목코드
        <input :value="symbol" type="text" disabled />
      </label>

      <label>
        수량
        <input v-model.number="qty" type="number" min="1" step="1" />
      </label>

      <label>
        평단가
        <input v-model.number="avgPrice" type="number" min="0" step="1" />
      </label>

      <p v-if="errorMessage" class="error">{{ errorMessage }}</p>

      <div class="modal-actions">
        <button class="btn" type="button" @click="emit('close')">취소</button>
        <button class="btn btn-primary" type="button" @click="submit">저장</button>
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
  width: 420px;
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
