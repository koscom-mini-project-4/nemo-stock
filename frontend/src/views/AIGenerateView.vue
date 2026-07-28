<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { generateDraft } from '@/api/services'
import type { GenerateDraftResponse } from '@/api/types'
import { useDraftStore } from '@/stores/draft'

const idea = ref('')
const universeText = ref('')
const loading = ref(false)
const errorMessage = ref('')
const draft = ref<GenerateDraftResponse | null>(null)

const router = useRouter()
const draftStore = useDraftStore()

interface IdeaTemplate {
  label: string
  idea: string
  universe?: string
}

const IDEA_TEMPLATES: IdeaTemplate[] = [
  {
    label: '뉴스 긍정 + 상승 종목 매수',
    idea: '최근 뉴스가 긍정적이고 전일 대비 상승한 종목을 매수하고 싶다',
  },
  {
    label: '이동평균선 상향 돌파 매수 + 손절',
    idea: '20일 이동평균선을 상향 돌파하면 매수하고, 매수가 대비 5% 하락하면 손절하고 싶다',
  },
  {
    label: 'RSI 과매도 매수 + 목표수익 청산',
    idea: 'RSI가 30 이하로 과매도 구간에 진입하면 매수하고, 매수가 대비 3% 상승하면 목표수익으로 매도하고 싶다',
  },
  {
    label: '공시 호재 반응 매매',
    idea: '실적 관련 공시가 긍정적으로 평가되는 종목을 매수하고 싶다',
    universe: '005930,000660',
  },
]

function applyTemplate(template: IdeaTemplate) {
  idea.value = template.idea
  if (template.universe) universeText.value = template.universe
}

const elapsedSec = ref(0)
let elapsedTimer: ReturnType<typeof setInterval> | null = null

function startElapsedTimer() {
  elapsedSec.value = 0
  elapsedTimer = setInterval(() => {
    elapsedSec.value += 1
  }, 1000)
}

function stopElapsedTimer() {
  if (elapsedTimer) {
    clearInterval(elapsedTimer)
    elapsedTimer = null
  }
}

async function submit() {
  if (!idea.value.trim()) return
  loading.value = true
  errorMessage.value = ''
  draft.value = null
  startElapsedTimer()
  try {
    const universe = universeText.value
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
    draft.value = await generateDraft(idea.value, universe.length ? universe : undefined)
  } catch (err) {
    const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
    errorMessage.value =
      typeof detail === 'string'
        ? detail
        : detail
          ? JSON.stringify(detail)
          : 'AI 초안 생성에 실패했습니다. OPENAI_API_KEY 설정을 확인하세요.'
  } finally {
    loading.value = false
    stopElapsedTimer()
  }
}

function editOnCanvas() {
  if (!draft.value) return
  draftStore.setDraft(draft.value.name, draft.value.graph)
  router.push('/strategies/new')
}
</script>

<template>
  <div class="ai-generate">
    <h1>AI 전략 초안 생성</h1>
    <p class="text-muted">
      투자 아이디어를 자연어로 입력하면 AI가 노드 워크플로 초안을 만듭니다. 생성된 초안은 저장되지
      않으며, 검토 후 캔버스에서 수정해 저장해야 합니다.
    </p>

    <div class="card form">
      <div class="templates">
        <span class="templates-label">예시로 시작하기</span>
        <div class="templates-buttons">
          <button
            v-for="template in IDEA_TEMPLATES"
            :key="template.label"
            class="btn template-btn"
            type="button"
            @click="applyTemplate(template)"
          >
            {{ template.label }}
          </button>
        </div>
      </div>
      <label>
        투자 아이디어
        <textarea
          v-model="idea"
          rows="3"
          placeholder="예) 최근 뉴스가 긍정적이고 전일 대비 상승한 종목을 매수하고 싶다"
        />
      </label>
      <label>
        대상 종목코드 (콤마 구분, 선택)
        <input v-model="universeText" type="text" placeholder="005930,000660" />
      </label>
      <button class="btn btn-primary" :disabled="loading || !idea.trim()" @click="submit">
        {{ loading ? '생성 중...' : '초안 생성' }}
      </button>
      <p v-if="loading" class="text-muted elapsed">AI 응답 대기 중... ({{ elapsedSec }}초 경과)</p>
      <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
    </div>

    <div v-if="draft" class="card preview">
      <h2>{{ draft.name }}</h2>
      <p class="disclaimer">⚠ {{ draft.disclaimer }}</p>
      <ul class="node-list">
        <li v-for="node in draft.graph.nodes" :key="node.id">
          <span class="mono">{{ node.id }}</span> — {{ node.type }}
        </li>
      </ul>
      <p v-if="draft.usage" class="text-muted usage-line">
        토큰 {{ draft.usage.total_tokens.toLocaleString() }}개 사용
        (prompt {{ draft.usage.prompt_tokens.toLocaleString() }} / completion
        {{ draft.usage.completion_tokens.toLocaleString() }})
      </p>
      <button class="btn btn-primary" @click="editOnCanvas">캔버스에서 편집</button>
    </div>
  </div>
</template>

<style scoped>
.ai-generate {
  padding: 24px;
  max-width: 700px;
  margin: 0 auto;
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

h1 {
  font-size: 20px;
  margin: 0;
}

.form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.form label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
  color: var(--text-muted);
}

.error {
  color: var(--danger);
  margin: 0;
}

.templates {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 4px;
}

.templates-label {
  font-size: 12px;
  color: var(--text-muted);
}

.templates-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.template-btn {
  font-size: 12.5px;
}

.preview h2 {
  margin: 0 0 8px;
  font-size: 16px;
}

.disclaimer {
  background: #fef3c7;
  color: #92400e;
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 13px;
}

.elapsed {
  font-size: 12px;
  margin: 6px 0 0;
}

.usage-line {
  font-size: 12px;
  margin: 6px 0;
}

.node-list {
  margin: 10px 0;
  padding-left: 18px;
  font-size: 13px;
}
</style>
