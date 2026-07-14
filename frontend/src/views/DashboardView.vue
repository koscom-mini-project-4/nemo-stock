<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { deleteWorkflow, fetchWorkflows, updateWorkflow } from '@/api/services'
import type { WorkflowOut } from '@/api/types'

const workflows = ref<WorkflowOut[]>([])
const loading = ref(true)
const router = useRouter()

async function load() {
  loading.value = true
  try {
    workflows.value = await fetchWorkflows()
  } finally {
    loading.value = false
  }
}

async function toggleActive(wf: WorkflowOut) {
  const nextStatus = wf.status === 'active' ? 'inactive' : 'active'
  try {
    await updateWorkflow(wf.id, { status: nextStatus })
    await load()
  } catch {
    alert('상태 변경에 실패했습니다. 그래프 검증 오류가 있는지 확인하세요.')
  }
}

async function remove(wf: WorkflowOut) {
  if (!confirm(`'${wf.name}' 전략을 삭제할까요?`)) return
  await deleteWorkflow(wf.id)
  await load()
}

function statusLabel(status: string) {
  return { draft: '초안', active: '실행 중', inactive: '중지' }[status] || status
}

onMounted(load)
</script>

<template>
  <div class="dashboard">
    <div class="dashboard-header">
      <h1>전략 대시보드</h1>
      <div class="actions">
        <RouterLink class="btn" to="/ai/generate">AI로 전략 생성</RouterLink>
        <RouterLink class="btn btn-primary" to="/strategies/new">새 전략 만들기</RouterLink>
      </div>
    </div>

    <p v-if="loading" class="text-muted">불러오는 중...</p>
    <p v-else-if="workflows.length === 0" class="text-muted">
      아직 전략이 없습니다. "새 전략 만들기"로 시작하세요.
    </p>

    <div v-else class="workflow-grid">
      <div v-for="wf in workflows" :key="wf.id" class="card workflow-card">
        <div class="workflow-card-head">
          <RouterLink :to="`/strategies/${wf.id}`" class="workflow-name">{{ wf.name }}</RouterLink>
          <span :class="['badge', `badge-${wf.status}`]">{{ statusLabel(wf.status) }}</span>
        </div>
        <p class="text-muted">
          노드 {{ wf.graph.nodes.length }}개 · 주기 {{ wf.schedule_interval_sec }}초 · 수정 {{ new Date(wf.updated_at).toLocaleString() }}
        </p>
        <div class="workflow-card-actions">
          <button class="btn" @click="router.push(`/strategies/${wf.id}`)">편집</button>
          <button class="btn" @click="toggleActive(wf)">
            {{ wf.status === 'active' ? '중지' : '활성화' }}
          </button>
          <button class="btn btn-danger" @click="remove(wf)">삭제</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dashboard {
  padding: 24px;
  max-width: 1100px;
  margin: 0 auto;
  width: 100%;
}

.dashboard-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.dashboard-header h1 {
  font-size: 22px;
  margin: 0;
}

.actions {
  display: flex;
  gap: 8px;
}

.workflow-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 14px;
}

.workflow-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.workflow-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.workflow-name {
  font-weight: 600;
  text-decoration: none;
  color: var(--text);
}

.workflow-card-actions {
  display: flex;
  gap: 6px;
  margin-top: 4px;
}
</style>
