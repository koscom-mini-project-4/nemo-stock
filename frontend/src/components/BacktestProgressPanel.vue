<script setup lang="ts">
import { computed } from 'vue'
import type { NodeEventOut } from '@/api/types'

const props = defineProps<{ events: NodeEventOut[] }>()

interface ProgressSnapshot {
  day: string | null
  dayIndex: number
  totalDays: number
  orders: number
  aiTokensDelta: number | null
}

function toSnapshot(e: NodeEventOut): ProgressSnapshot {
  const s = (e.output_snapshot ?? {}) as Record<string, unknown>
  return {
    day: (s.day as string | undefined) ?? null,
    dayIndex: (s.day_index as number | undefined) ?? 0,
    totalDays: (s.total_days as number | undefined) ?? 0,
    orders: (s.orders as number | undefined) ?? 0,
    aiTokensDelta: (s.ai_tokens_delta as number | null | undefined) ?? null,
  }
}

const snapshots = computed(() => props.events.map(toSnapshot))
const latest = computed(() => snapshots.value[snapshots.value.length - 1] ?? null)
const totalDays = computed(() => latest.value?.totalDays ?? 0)
const currentDayIndex = computed(() => latest.value?.dayIndex ?? 0)
const percent = computed(() => (totalDays.value ? Math.round((currentDayIndex.value / totalDays.value) * 100) : 0))
const hasTokenData = computed(() => snapshots.value.some((s) => s.aiTokensDelta !== null))
const totalTokens = computed(() => snapshots.value.reduce((sum, s) => sum + (s.aiTokensDelta ?? 0), 0))
</script>

<template>
  <div class="progress-panel">
    <div class="progress-head">
      <span>백테스트 진행 중...</span>
      <span class="text-muted">{{ currentDayIndex }} / {{ totalDays || '?' }}일</span>
    </div>
    <div class="progress-bar">
      <div class="progress-bar-fill" :style="{ width: percent + '%' }" />
    </div>
    <div v-if="hasTokenData" class="text-muted token-line">누적 AI 토큰 사용량: {{ totalTokens.toLocaleString() }}개</div>
    <div class="progress-log">
      <p v-if="snapshots.length === 0" class="text-muted">진행 신호를 기다리는 중...</p>
      <div v-for="(s, i) in snapshots" :key="i" class="progress-log-line mono">
        <template v-if="s.day">
          {{ s.day }} 처리 완료 ({{ s.dayIndex }}/{{ s.totalDays }}) · 주문 {{ s.orders }}건
          <template v-if="s.aiTokensDelta !== null"> · 토큰 {{ s.aiTokensDelta.toLocaleString() }}개</template>
        </template>
        <template v-else>백테스트 시작 — 총 {{ s.totalDays }}거래일</template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.progress-panel {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 10px 0;
}

.progress-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  font-weight: 600;
}

.progress-bar {
  height: 6px;
  border-radius: 3px;
  background: var(--bg);
  overflow: hidden;
}

.progress-bar-fill {
  height: 100%;
  background: var(--accent);
  transition: width 0.2s ease;
}

.token-line {
  font-size: 12px;
}

.progress-log {
  max-height: 140px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 3px;
  font-size: 11.5px;
  background: var(--bg);
  border-radius: 6px;
  padding: 8px;
}

.progress-log-line {
  color: var(--text-muted);
}
</style>
