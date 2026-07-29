<script setup lang="ts">
/**
 * "새 전략" 시작 페이지 — nemo-poc의 NewStrategyPage처럼 빈 캔버스/AI 초안/템플릿 세 가지
 * 시작 방법을 한 페이지에 모은다(기존에는 빈 캔버스는 /strategies/new가 바로 열고, AI 생성은
 * /ai/generate 별도 페이지, 템플릿은 대시보드에 흩어져 있었음).
 */
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { fetchWorkflowTemplates } from '@/api/services'
import { postSSE } from '@/api/sse'
import type { GenerateDraftResponse, WorkflowTemplateOut } from '@/api/types'
import { useDraftStore } from '@/stores/draft'
import SymbolAutocomplete from '@/components/SymbolAutocomplete.vue'

const router = useRouter()
const draftStore = useDraftStore()

function goBlankCanvas() {
  router.push('/strategies/new/canvas')
}

// 템플릿으로 시작하기
const templates = ref<WorkflowTemplateOut[]>([])
async function loadTemplates() {
  templates.value = await fetchWorkflowTemplates().catch(() => [])
}
function useTemplate(template: WorkflowTemplateOut) {
  draftStore.setDraft(template.name, template.graph)
  router.push('/strategies/new/canvas')
}

// AI로 초안 만들기 (기존 AIGenerateView.vue 로직 그대로 이식 — 예시 프롬프트 자동완성 버튼 포함)
const idea = ref('')
const universeText = ref('')
const loading = ref(false)
const errorMessage = ref('')
const draft = ref<GenerateDraftResponse | null>(null)
const streamingPreview = ref('')

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
  {
    label: '뉴스+AI 확신도 매수, 익절/손절/보유기간/포지션 관리',
    idea:
      '삼성전자와 SK하이닉스를 대상으로, 실적 관련 긍정적 뉴스가 나오고 AI 확신도가 0.7 이상이면 ' +
      '매수해줘. 5% 오르면 익절, 3% 빠지면 손절하고, 최대 10일 보유. 종목당 자본의 5%씩 투입하고 ' +
      '동시에 최대 5종목까지만 보유해. 전체 포트폴리오 손실이 15%를 넘으면 전략을 자동으로 멈춰줘.',
    universe: '005930,000660',
  },
  {
    label: 'RSI+이동평균 눌림목 매수, 비중 제한',
    idea:
      'RSI가 30 이하로 과매도이면서 20일 이동평균선이 여전히 상승 추세일 때 매수해줘. 종목당 최대 ' +
      '비중은 전체 자산의 10%로 제한하고, 매수가 대비 7% 하락하면 손절해줘.',
  },
  {
    label: '거래량 급증 + 공시 호재, 이동평균 이탈 시 청산',
    idea:
      '실적 공시가 긍정적으로 평가되고 거래량이 평소보다 2배 이상 터진 종목만 매수해줘. 매수 후 ' +
      '20일 이동평균선 아래로 떨어지면 전량 매도하고, 매수가 대비 10% 상승하면 익절해줘.',
  },
  {
    label: '섹터 모멘텀 + 거시 리스크 회피',
    idea:
      '반도체 섹터 모멘텀이 강할 때만 매수하고, 거시 리스크 지표가 위험 신호를 보내면 즉시 전량 ' +
      '매도해줘. 매수 후 최대 15일 보유, 3% 손절·5% 익절 기준을 적용하고 한 번에 최대 3종목까지만 ' +
      '보유해줘.',
  },
  {
    label: '볼린저밴드 상단 돌파 + 거래량 급증',
    idea:
      '볼린저밴드 상단을 돌파하면서 거래량이 급증한 종목을 매수해줘. 매수가 대비 4% 상승하면 익절, ' +
      '2% 하락하면 손절하고 종목당 자본의 8%씩 투입해줘. 전체 포트폴리오가 -10% 손실이면 신규 ' +
      '매수를 멈춰줘.',
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
  streamingPreview.value = ''
  startElapsedTimer()
  const universe = universeText.value
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
  try {
    await postSSE<GenerateDraftResponse>(
      '/ai/generate-draft/stream',
      { idea: idea.value, universe: universe.length ? universe : undefined },
      {
        onChunk: (text) => {
          streamingPreview.value += text
        },
        onResult: (result) => {
          draft.value = result
        },
        onError: (detail) => {
          errorMessage.value =
            typeof detail === 'string'
              ? detail
              : detail
                ? JSON.stringify(detail)
                : 'AI 초안 생성에 실패했습니다. OPENAI_API_KEY 설정을 확인하세요.'
        },
      },
    )
  } finally {
    loading.value = false
    streamingPreview.value = ''
    stopElapsedTimer()
  }
}

function editOnCanvas() {
  if (!draft.value) return
  draftStore.setDraft(draft.value.name, draft.value.graph)
  router.push('/strategies/new/canvas')
}

onMounted(loadTemplates)
</script>

<template>
  <div class="new-strategy">
    <div class="quickstart-blank">
      <div class="quickstart-blank__text">
        <h2>빈 전략 만들기</h2>
        <p class="text-muted">아무것도 없는 캔버스에서 노드를 직접 배치하며 자유롭게 전략을 설계합니다.</p>
      </div>
      <button class="btn btn-primary btn-lg" type="button" @click="goBlankCanvas">빈 캔버스 열기</button>
    </div>

    <div class="quickstart-ai">
      <div>
        <h2>AI로 초안 만들기</h2>
        <p class="text-muted">
          투자 아이디어를 자연어로 입력하면 AI가 노드 워크플로 초안을 만듭니다. 생성된 초안은 저장되지
          않으며, 검토 후 캔버스에서 수정해 저장해야 합니다.
        </p>
      </div>

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

      <div class="quickstart-ai__form">
        <label class="ai-field">
          투자 아이디어
          <textarea
            v-model="idea"
            class="quickstart-ai__input"
            rows="3"
            placeholder="예) 최근 뉴스가 긍정적이고 전일 대비 상승한 종목을 매수하고 싶다"
          />
        </label>
        <label class="ai-field">
          대상 종목코드 (콤마 구분, 선택)
          <SymbolAutocomplete v-model="universeText" />
        </label>
        <button class="btn btn-primary" :disabled="loading || !idea.trim()" @click="submit">
          {{ loading ? '생성 중...' : '초안 생성' }}
        </button>
      </div>

      <div v-if="loading" class="streaming-preview">
        <p class="text-muted elapsed">AI가 작성 중입니다... ({{ elapsedSec }}초 경과)</p>
        <pre v-if="streamingPreview" class="mono preview-text">{{ streamingPreview }}</pre>
      </div>
      <p v-if="errorMessage" class="error">{{ errorMessage }}</p>

      <div v-if="draft" class="card preview">
        <h3>{{ draft.name }}</h3>
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

    <section>
      <div class="section-header">
        <h2>템플릿으로 시작하기</h2>
      </div>
      <p v-if="templates.length === 0" class="text-muted">불러올 템플릿이 없습니다.</p>
      <div v-else class="template-grid">
        <div v-for="tpl in templates" :key="tpl.id" class="card template-card">
          <h3>{{ tpl.name }}</h3>
          <p class="text-muted">{{ tpl.description }}</p>
          <button class="btn btn-primary" type="button" @click="useTemplate(tpl)">이 템플릿으로 시작하기</button>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.new-strategy {
  padding: 24px clamp(20px, 4vw, 48px) 48px;
  max-width: 1100px;
  margin: 0 auto;
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 28px;
}

.quickstart-blank {
  display: flex;
  align-items: center;
  gap: 20px;
  background: var(--surface);
  border: 1px dashed var(--border);
  border-radius: 4px;
  padding: 24px 28px;
  box-shadow: 0 3px 14px rgba(24, 49, 88, 0.06);
}

.quickstart-blank__text {
  flex: 1;
  min-width: 0;
}

.quickstart-blank__text h2 {
  margin: 0 0 4px;
}

.quickstart-blank__text p {
  margin: 0;
}

.btn-lg {
  min-height: 46px;
  padding: 11px 22px;
  font-size: 15px;
}

.quickstart-ai {
  display: flex;
  flex-direction: column;
  gap: 16px;
  background: var(--surface);
  border: 1px dashed var(--border);
  border-radius: 4px;
  padding: 24px 28px;
  box-shadow: 0 3px 14px rgba(24, 49, 88, 0.06);
}

.quickstart-ai h2 {
  margin: 0 0 4px;
}

.quickstart-ai > div > p {
  margin: 0;
}

.templates {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
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
  min-height: 30px;
  padding: 5px 10px;
}

.quickstart-ai__form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.ai-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
  color: var(--text-muted);
}

.quickstart-ai__input {
  resize: vertical;
}

.error {
  color: var(--danger);
  margin: 0;
}

.preview h3 {
  margin: 0 0 8px;
  font-size: 16px;
}

.disclaimer {
  background: var(--accent-soft);
  color: var(--accent-hover);
  border: 1px solid var(--accent-soft-border);
  padding: 8px 10px;
  border-radius: 3px;
  font-size: 13px;
}

.elapsed {
  font-size: 12px;
  margin: 6px 0 0;
}

.streaming-preview {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.preview-text {
  margin: 0;
  max-height: 160px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--text-muted);
  background: var(--bg);
  border-radius: 3px;
  padding: 8px 10px;
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

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.section-header h2 {
  margin: 0;
}

.template-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 16px;
}

.template-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.template-card h3 {
  margin: 0;
  font-size: 16px;
}

.template-card p {
  flex: 1;
  margin: 0;
  line-height: 1.5;
}
</style>
