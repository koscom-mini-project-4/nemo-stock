<script setup lang="ts">
import type { ValidationResult } from '@/api/types'

defineProps<{
  result: ValidationResult | null
  loading: boolean
}>()
</script>

<template>
  <div class="validation-panel">
    <p v-if="loading" class="text-muted">검증 중...</p>
    <p v-else-if="!result" class="text-muted">"검증" 버튼을 눌러 그래프를 확인하세요.</p>
    <template v-else>
      <p v-if="result.valid" class="ok">✔ 유효한 워크플로입니다.</p>
      <ul v-else class="errors">
        <li v-for="(err, i) in result.errors" :key="i">{{ err }}</li>
      </ul>
      <div v-if="result.execution_order.length" class="order">
        <div class="text-muted">실행 순서</div>
        <div class="mono">{{ result.execution_order.join(' → ') }}</div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.validation-panel {
  padding: 12px;
}

.ok {
  color: var(--success);
  font-weight: 600;
}

.errors {
  color: var(--danger);
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
}

.errors li {
  margin-bottom: 4px;
}

.order {
  margin-top: 12px;
}
</style>
