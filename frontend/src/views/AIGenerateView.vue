<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { generateDraft } from '@/api/services'
import type { GenerateDraftResponse } from '@/api/types'
import { useDraftStore } from '@/stores/draft'
import SymbolAutocomplete from '@/components/SymbolAutocomplete.vue'

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
        <SymbolAutocomplete v-model="universeText" />
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
