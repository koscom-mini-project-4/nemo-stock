<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  fetchAdminMetrics,
  fetchNewsAnalyzed,
  fetchNewsClusters,
  fetchNewsPending,
  fetchNewsStats,
  fetchNewsTopicClusters,
  fetchNewsTopicKeys,
  fetchSymbolStats,
  syncSymbols,
  triggerNewsUpdate,
} from '@/api/services'
import type {
  AdminMetrics,
  AnalyzedNewsItem,
  NewsCluster,
  NewsStats,
  NewsTopicCluster,
  NewsTopicGroup,
  NewsUpdateResult,
  PendingNewsResult,
  SymbolStats,
} from '@/api/types'
import { formatUsd } from '@/utils/format'

type Section = 'usage' | 'symbols' | 'news' | 'explore' | 'analyzed' | 'pending'

const SECTIONS: { value: Section; label: string }[] = [
  { value: 'usage', label: '사용량 통계' },
  { value: 'symbols', label: '종목 마스터' },
  { value: 'news', label: '뉴스 분석 현황' },
  { value: 'explore', label: '종목·섹터·거시 탐색' },
  { value: 'analyzed', label: '분석된 뉴스' },
  { value: 'pending', label: '미분석 뉴스' },
]

const activeSection = ref<Section>('usage')
const sidebarOpen = ref(true)

const metrics = ref<AdminMetrics | null>(null)
const metricsLoading = ref(false)
const metricsError = ref('')

const symbolStats = ref<SymbolStats | null>(null)
const symbolStatsLoading = ref(false)
const symbolStatsError = ref('')
const symbolSyncing = ref(false)
const symbolSyncMessage = ref('')
const symbolSyncError = ref('')

const newsStats = ref<NewsStats | null>(null)
const newsStatsLoading = ref(false)
const newsStatsError = ref('')

const clusterStart = ref(defaultStart())
const clusterEnd = ref(defaultEnd())
const clusters = ref<NewsCluster[]>([])
const clustersLoading = ref(false)
const clustersError = ref('')

const updating = ref(false)
const updateResult = ref<NewsUpdateResult | null>(null)
const updateError = ref('')
const updateDays = ref('')
const updateKeywords = ref('')

const TOPIC_AXES: { value: NewsTopicGroup; label: string }[] = [
  { value: 'stock', label: '종목' },
  { value: 'sector', label: '섹터' },
  { value: 'macro', label: '거시경제' },
]

const topicGroup = ref<NewsTopicGroup>('stock')
const topicKeys = ref<string[]>([])
const topicKeysLoading = ref(false)
const topicKeysError = ref('')

const selectedTopicKey = ref('')
const topicClusters = ref<NewsTopicCluster[]>([])
const topicClustersLoading = ref(false)
const topicClustersError = ref('')

const analyzedNews = ref<AnalyzedNewsItem[]>([])
const analyzedNewsLoading = ref(false)
const analyzedNewsError = ref('')

const pendingNews = ref<PendingNewsResult | null>(null)
const pendingNewsLoading = ref(false)
const pendingNewsError = ref('')

function defaultEnd() {
  return new Date().toISOString().slice(0, 10)
}
function defaultStart() {
  const d = new Date()
  d.setDate(d.getDate() - 7)
  return d.toISOString().slice(0, 10)
}

async function loadMetrics() {
  metricsLoading.value = true
  metricsError.value = ''
  try {
    metrics.value = await fetchAdminMetrics()
  } catch {
    metricsError.value = '사용량 통계를 불러오지 못했습니다.'
  } finally {
    metricsLoading.value = false
  }
}

async function loadSymbolStats() {
  symbolStatsLoading.value = true
  symbolStatsError.value = ''
  try {
    symbolStats.value = await fetchSymbolStats()
  } catch {
    symbolStatsError.value = '종목 마스터 현황을 불러오지 못했습니다.'
  } finally {
    symbolStatsLoading.value = false
  }
}

async function runSymbolSync() {
  symbolSyncing.value = true
  symbolSyncError.value = ''
  symbolSyncMessage.value = ''
  try {
    const result = await syncSymbols()
    const sourceLabel = result.source === 'koscom' ? 'KOSCOM CHECK-API' : '공공데이터포털'
    symbolSyncMessage.value = `${result.as_of} 기준 ${result.synced.toLocaleString()}개 종목 동기화 완료 (${sourceLabel})`
    await loadSymbolStats()
  } catch (err) {
    const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    symbolSyncError.value = detail || '종목 마스터 동기화에 실패했습니다.'
  } finally {
    symbolSyncing.value = false
  }
}

async function loadNewsStats() {
  newsStatsLoading.value = true
  newsStatsError.value = ''
  try {
    newsStats.value = await fetchNewsStats()
  } catch {
    newsStatsError.value = '뉴스 분석 현황을 불러오지 못했습니다.'
  } finally {
    newsStatsLoading.value = false
  }
}

async function loadClusters() {
  clustersLoading.value = true
  clustersError.value = ''
  try {
    clusters.value = await fetchNewsClusters(clusterStart.value, clusterEnd.value)
  } catch {
    clustersError.value = '클러스터 목록을 불러오지 못했습니다.'
  } finally {
    clustersLoading.value = false
  }
}

function reloadClusterRange() {
  loadClusters()
  loadTopicKeys()
}

interface TopicTag {
  key: string
  group: NewsTopicGroup
}

function clusterTagRows(c: NewsCluster): TopicTag[] {
  return [
    ...(c.종목 ?? []).map((key) => ({ key, group: 'stock' as const })),
    ...(c.섹터 ?? []).map((key) => ({ key, group: 'sector' as const })),
    ...(c.거시지표 ?? []).map((key) => ({ key, group: 'macro' as const })),
  ]
}

function newsTagRows(n: AnalyzedNewsItem): TopicTag[] {
  return [
    ...n.stocks.map((key) => ({ key, group: 'stock' as const })),
    ...n.sectors.map((key) => ({ key, group: 'sector' as const })),
    ...n.macros.map((key) => ({ key, group: 'macro' as const })),
  ]
}

// 백엔드 db.py::GROUPS의 그룹 코드(A/B/C, "그룹행수" 통계 키)와 프론트 축 값(stock/sector/macro)
// 매핑. NewsTopicGroup 자체는 이미 있으니 여기서는 통계 응답 키 변환용으로만 쓴다.
const AXIS_GROUP_CODE: Record<NewsTopicGroup, string> = { stock: 'A', sector: 'B', macro: 'C' }

/** "종목/섹터/거시로 클러스터 탐색" 탭으로 이동해 특정 키(예: "삼성전자")를 바로 조회한다
 * — 뉴스 분석 현황/분석된 뉴스 표의 태그를 눌렀을 때 쓴다. */
async function exploreTag(key: string, group: NewsTopicGroup) {
  activeSection.value = 'explore'
  topicGroup.value = group
  await loadTopicKeys()
  // 클릭한 태그가 현재 조회 기간(clusterStart~clusterEnd) 밖의 클러스터에서 왔을 수도 있어
  // 목록에 없으면 직접 끼워 넣는다 — 그래야 <select>가 빈 값이 아니라 이 키를 보여준다.
  if (!topicKeys.value.includes(key)) {
    topicKeys.value = [...topicKeys.value, key].sort()
  }
  selectedTopicKey.value = key
  await loadTopicClusters()
}

/** "그룹행수" 통계 타일을 눌렀을 때 — 특정 키 없이 탐색 탭의 축만 맞춰준다. */
function goToAxis(group: NewsTopicGroup) {
  activeSection.value = 'explore'
  if (topicGroup.value !== group) {
    topicGroup.value = group
    loadTopicKeys()
  }
}

// 백엔드 NewsTrader.stats()(app/vendor/news_classifier/db.py::overview)가 내려주는 원시 dict
// 모양 — 공유 타입(NewsStats)은 벤더 라이브러리 내부 구현에 묶이지 않도록 의도적으로
// Record<string, unknown>이라, 화면에 카드/막대그래프로 그리기 위해 여기서만 구체 타입으로 본다.
interface NewsOverview {
  뉴스?: number
  클러스터?: number
  분류행?: number
  기간?: [string | null, string | null]
  strength분포?: [number, number][]
  그룹행수?: Record<string, number>
}

const overview = computed(() => newsStats.value as NewsOverview | null)

const maxStrengthCount = computed(() => {
  const dist = overview.value?.strength분포 ?? []
  return Math.max(1, ...dist.map(([, count]) => count))
})

function strengthTone(bucket: number): 'positive' | 'negative' | 'neutral' {
  if (bucket > 0.05) return 'positive'
  if (bucket < -0.05) return 'negative'
  return 'neutral'
}

async function loadTopicKeys() {
  topicKeysLoading.value = true
  topicKeysError.value = ''
  selectedTopicKey.value = ''
  topicClusters.value = []
  try {
    topicKeys.value = await fetchNewsTopicKeys(topicGroup.value, clusterStart.value, clusterEnd.value)
  } catch {
    topicKeysError.value = '키 목록을 불러오지 못했습니다.'
    topicKeys.value = []
  } finally {
    topicKeysLoading.value = false
  }
}

async function loadTopicClusters() {
  if (!selectedTopicKey.value) return
  topicClustersLoading.value = true
  topicClustersError.value = ''
  try {
    topicClusters.value = await fetchNewsTopicClusters(
      topicGroup.value,
      selectedTopicKey.value,
      clusterStart.value,
      clusterEnd.value,
    )
  } catch {
    topicClustersError.value = '클러스터 목록을 불러오지 못했습니다.'
  } finally {
    topicClustersLoading.value = false
  }
}

async function loadAnalyzedNews() {
  analyzedNewsLoading.value = true
  analyzedNewsError.value = ''
  try {
    analyzedNews.value = await fetchNewsAnalyzed()
  } catch {
    analyzedNewsError.value = '분석된 뉴스 목록을 불러오지 못했습니다.'
  } finally {
    analyzedNewsLoading.value = false
  }
}

async function loadPendingNews() {
  pendingNewsLoading.value = true
  pendingNewsError.value = ''
  try {
    pendingNews.value = await fetchNewsPending()
  } catch {
    pendingNewsError.value = '미분석 뉴스 목록을 불러오지 못했습니다.'
  } finally {
    pendingNewsLoading.value = false
  }
}

async function runUpdate(force: boolean) {
  updating.value = true
  updateError.value = ''
  updateResult.value = null
  try {
    const days = updateDays.value.trim() ? Number(updateDays.value) : undefined
    const keywords = updateKeywords.value
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
    updateResult.value = await triggerNewsUpdate(force, {
      days,
      keywords: keywords.length ? keywords : undefined,
    })
    // 갱신 후 현황도 같이 새로고침한다.
    await Promise.all([loadNewsStats(), loadClusters(), loadAnalyzedNews(), loadPendingNews()])
  } catch (err) {
    const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    updateError.value = detail || '뉴스 갱신에 실패했습니다.'
  } finally {
    updating.value = false
  }
}

onMounted(() => {
  loadMetrics()
  loadSymbolStats()
  loadNewsStats()
  loadClusters()
  loadTopicKeys()
  loadAnalyzedNews()
  loadPendingNews()
})
</script>

<template>
  <div class="admin-view">
    <h1>관리자</h1>

    <div class="admin-layout" :class="{ 'sidebar-collapsed': !sidebarOpen }">
      <nav class="admin-sidebar">
        <button
          class="sidebar-toggle"
          type="button"
          :title="sidebarOpen ? '메뉴 접기' : '메뉴 펼치기'"
          @click="sidebarOpen = !sidebarOpen"
        >
          <span>{{ sidebarOpen ? '◂' : '▸' }}</span>
          <span v-if="sidebarOpen" class="sidebar-toggle-label">메뉴 접기</span>
        </button>
        <template v-if="sidebarOpen">
          <button
            v-for="s in SECTIONS"
            :key="s.value"
            type="button"
            class="sidebar-item"
            :class="{ active: activeSection === s.value }"
            @click="activeSection = s.value"
          >
            {{ s.label }}
          </button>
        </template>
      </nav>

      <div class="admin-content">
        <div v-if="activeSection === 'usage'" class="card">
          <h2>사용량 통계</h2>
          <p v-if="metricsError" class="error">{{ metricsError }}</p>
          <p v-else-if="metricsLoading" class="text-muted">불러오는 중...</p>
          <template v-else-if="metrics">
            <div class="metric-grid">
              <div class="metric">
                <div class="text-muted">백테스트 실행 수</div>
                <div class="metric-value">{{ metrics.backtest_count }}</div>
              </div>
              <div class="metric">
                <div class="text-muted">AI 호출 수</div>
                <div class="metric-value">{{ metrics.ai_usage.total_calls }}</div>
              </div>
              <div class="metric">
                <div class="text-muted">총 토큰(prompt+completion)</div>
                <div class="metric-value">{{ metrics.ai_usage.total_tokens.toLocaleString() }}</div>
              </div>
              <div class="metric">
                <div class="text-muted">prompt / completion</div>
                <div class="metric-value small">
                  {{ metrics.ai_usage.prompt_tokens.toLocaleString() }} /
                  {{ metrics.ai_usage.completion_tokens.toLocaleString() }}
                </div>
              </div>
              <div class="metric">
                <div class="text-muted">추정 비용(USD)</div>
                <div class="metric-value">{{ formatUsd(metrics.ai_usage.total_cost_usd) }}</div>
              </div>
            </div>
            <p v-if="metrics.ai_usage.total_unpriced_tokens > 0" class="text-muted cost-note">
              가격표에 없는 모델의 토큰 {{ metrics.ai_usage.total_unpriced_tokens.toLocaleString() }}개는
              위 추정 비용에 포함되지 않았습니다(하한 추정치). 또한 캐시 히트 여부를 기록하지 않아
              prompt 토큰 전체를 표준(비캐시) 단가로 계산합니다 — 실제 비용은 이보다 낮을 수 있습니다.
            </p>

            <div class="breakdown-row">
              <div class="breakdown">
                <div class="breakdown-title">목적별</div>
                <table>
                  <thead><tr><th>purpose</th><th>호출</th><th>토큰</th><th>비용(USD)</th></tr></thead>
                  <tbody>
                    <tr v-for="b in metrics.ai_usage.by_purpose" :key="b.purpose">
                      <td class="mono">{{ b.purpose }}</td>
                      <td>{{ b.calls }}</td>
                      <td>{{ b.total_tokens.toLocaleString() }}</td>
                      <td>
                        {{ formatUsd(b.cost_usd ?? 0) }}
                        <span v-if="b.unpriced_tokens" class="text-muted small">(+{{ b.unpriced_tokens.toLocaleString() }} 미가격)</span>
                      </td>
                    </tr>
                    <tr v-if="metrics.ai_usage.by_purpose.length === 0"><td colspan="4" class="text-muted">기록 없음</td></tr>
                  </tbody>
                </table>
              </div>
              <div class="breakdown">
                <div class="breakdown-title">모델별</div>
                <table>
                  <thead><tr><th>model</th><th>호출</th><th>토큰</th><th>비용(USD)</th></tr></thead>
                  <tbody>
                    <tr v-for="b in metrics.ai_usage.by_model" :key="b.model">
                      <td class="mono">{{ b.model }}</td>
                      <td>{{ b.calls }}</td>
                      <td>{{ b.total_tokens.toLocaleString() }}</td>
                      <td>{{ b.cost_usd === null ? '가격 미상' : formatUsd(b.cost_usd) }}</td>
                    </tr>
                    <tr v-if="metrics.ai_usage.by_model.length === 0"><td colspan="4" class="text-muted">기록 없음</td></tr>
                  </tbody>
                </table>
              </div>
            </div>
          </template>
        </div>

        <div v-if="activeSection === 'symbols'" class="card">
          <div class="section-header">
            <h2>종목 마스터</h2>
            <button class="btn" :disabled="symbolSyncing" @click="runSymbolSync">
              {{ symbolSyncing ? '동기화 중...' : '지금 동기화' }}
            </button>
          </div>
          <p class="text-muted hint">
            공공데이터포털(금융위원회_주식시세정보)로 KOSPI/KOSDAQ 전 종목의 코드/종목명을
            가져와 캐시를 채웁니다. 그 응답이 비어 있으면(현재 서비스키 미승인 상태) KOSCOM
            CHECK-API로 자동 전환합니다. 동기화 전에는 대표 종목 8개만 사용됩니다(수 초 소요될
            수 있음). 이 캐시가 채워지면 `ai.news_signal`/`ai.free_prompt` 노드의 종목코드→종목명
            자동 매핑이 뉴스 분석 현황 검색과 같은 기준으로 훨씬 많은 종목에서 동작합니다.
          </p>
          <p v-if="symbolSyncError" class="error">{{ symbolSyncError }}</p>
          <p v-else-if="symbolSyncMessage" class="text-muted">{{ symbolSyncMessage }}</p>
          <p v-if="symbolStatsError" class="error">{{ symbolStatsError }}</p>
          <p v-else-if="symbolStatsLoading" class="text-muted">불러오는 중...</p>
          <div v-else-if="symbolStats" class="metric-grid">
            <div class="metric">
              <div class="text-muted">현재 캐시(조회용)</div>
              <div class="metric-value">{{ symbolStats.count.toLocaleString() }}</div>
            </div>
            <div class="metric">
              <div class="text-muted">DB 저장(직전 동기화)</div>
              <div class="metric-value">{{ symbolStats.db_count.toLocaleString() }}</div>
            </div>
          </div>
        </div>

        <div v-if="activeSection === 'news'" class="card news-card">
          <div class="section-header">
            <h2>뉴스 분석 현황</h2>
          </div>
          <div class="update-form">
            <div class="row">
              <label>
                기간(일, 선택)
                <input v-model="updateDays" type="number" min="1" placeholder="예: 5" />
              </label>
              <label class="grow">
                키워드(콤마 구분, 선택)
                <input v-model="updateKeywords" type="text" placeholder="예: 하이닉스,반도체,삼성" />
              </label>
            </div>
            <div class="actions">
              <button class="btn" :disabled="updating" @click="runUpdate(false)">
                {{ updating ? '갱신 중...' : '갱신(스로틀 적용)' }}
              </button>
              <button class="btn" :disabled="updating" @click="runUpdate(true)">지금 강제 갱신</button>
            </div>
          </div>
          <p v-if="updateError" class="error">{{ updateError }}</p>
          <p v-else-if="updateResult" class="text-muted">
            {{ updateResult.skipped ? '건너뜀(최근에 갱신됨)' : `수집 ${updateResult.collected ?? 0}건 · 분류 ${updateResult.classified ?? 0}건 · 삭제된 클러스터 ${updateResult.purged_clusters ?? 0}건` }}
          </p>
          <p class="text-muted hint">
            기본 갱신은 라이브러리 자체 쓰로틀(마지막 갱신 후 30분 이내면 건너뜀)이 적용되고, 강제
            갱신은 즉시 크롤링+AI 분류를 트리거합니다(수 분 소요될 수 있음). 기간/키워드를 입력하면
            이번 1회만 적용되고(전역 기본값은 그대로), 비워두면 라이브러리 기본 설정대로 동작합니다.
          </p>

          <p v-if="newsStatsError" class="error">{{ newsStatsError }}</p>
          <p v-else-if="newsStatsLoading" class="text-muted">불러오는 중...</p>
          <template v-else-if="overview">
            <div class="news-overview">
              <div class="overview-tile">
                <div class="overview-label">전체 뉴스</div>
                <div class="overview-value">{{ (overview.뉴스 ?? 0).toLocaleString() }}</div>
              </div>
              <div class="overview-tile">
                <div class="overview-label">클러스터(주제)</div>
                <div class="overview-value">{{ (overview.클러스터 ?? 0).toLocaleString() }}</div>
              </div>
              <div class="overview-tile">
                <div class="overview-label">AI 분류행</div>
                <div class="overview-value">{{ (overview.분류행 ?? 0).toLocaleString() }}</div>
              </div>
              <div class="overview-tile wide">
                <div class="overview-label">데이터 기간</div>
                <div class="overview-value date-range">
                  {{ overview.기간?.[0]?.slice(0, 10) ?? '-' }} ~ {{ overview.기간?.[1]?.slice(0, 10) ?? '-' }}
                </div>
              </div>
            </div>

            <div class="axis-tiles">
              <button
                v-for="axis in TOPIC_AXES"
                :key="axis.value"
                type="button"
                class="axis-tile"
                :class="axis.value"
                @click="goToAxis(axis.value)"
              >
                <div class="axis-tile-label">{{ axis.label }}</div>
                <div class="axis-tile-value">
                  {{ (overview.그룹행수?.[AXIS_GROUP_CODE[axis.value]] ?? 0).toLocaleString() }}
                </div>
                <div class="axis-tile-hint">탐색하기 →</div>
              </button>
            </div>

            <div class="strength-chart">
              <div class="strength-chart-title">뉴스 영향도(strength) 분포</div>
              <div class="strength-bars">
                <div v-for="[bucket, count] in overview.strength분포 ?? []" :key="bucket" class="strength-bar-col">
                  <div class="strength-bar-track">
                    <div
                      class="strength-bar-fill"
                      :class="strengthTone(bucket)"
                      :style="{ height: `${Math.max((count / maxStrengthCount) * 100, count > 0 ? 3 : 0)}%` }"
                    ></div>
                  </div>
                  <div class="strength-bar-count">{{ count.toLocaleString() }}</div>
                  <div class="strength-bar-label">{{ bucket > 0 ? '+' : '' }}{{ bucket }}</div>
                </div>
              </div>
            </div>
          </template>

          <div class="row cluster-range">
            <label>
              시작일
              <input v-model="clusterStart" type="date" />
            </label>
            <label>
              종료일
              <input v-model="clusterEnd" type="date" />
            </label>
            <button class="btn" :disabled="clustersLoading" @click="reloadClusterRange">조회</button>
          </div>
          <p v-if="clustersError" class="error">{{ clustersError }}</p>
          <table v-else class="cluster-table news-table">
            <thead><tr><th>대표제목</th><th>최초발생</th><th>strength</th><th>뉴스건수</th><th>관련 종목/섹터/거시</th></tr></thead>
            <tbody>
              <tr v-for="c in clusters" :key="c.id">
                <td>{{ c.representative_title }}</td>
                <td class="mono">{{ c.first_seen_at }}</td>
                <td>{{ c.strength }}</td>
                <td>{{ c.news_count }}</td>
                <td>
                  <button
                    v-for="tag in clusterTagRows(c)"
                    :key="`${tag.group}-${tag.key}`"
                    type="button"
                    class="tag"
                    :class="tag.group"
                    :title="`'${tag.key}' 관련 클러스터 탐색하기`"
                    @click="exploreTag(tag.key, tag.group)"
                  >
                    {{ tag.key }}
                  </button>
                  <span v-if="clusterTagRows(c).length === 0" class="text-muted">-</span>
                </td>
              </tr>
              <tr v-if="!clustersLoading && clusters.length === 0"><td colspan="5" class="text-muted">해당 기간에 클러스터가 없습니다.</td></tr>
            </tbody>
          </table>
        </div>

        <div v-if="activeSection === 'explore'" class="card">
          <h2>종목/섹터/거시로 클러스터 탐색</h2>
          <p class="text-muted hint">
            "뉴스 분석 현황"의 기간({{ clusterStart }} ~ {{ clusterEnd }})을 그대로 사용합니다.
            기간을 바꾸려면 그 화면의 조회란을 먼저 갱신하세요.
          </p>
          <div class="row">
            <label>
              축
              <select v-model="topicGroup" @change="loadTopicKeys">
                <option v-for="axis in TOPIC_AXES" :key="axis.value" :value="axis.value">{{ axis.label }}</option>
              </select>
            </label>
            <label>
              키
              <select v-model="selectedTopicKey" :disabled="topicKeysLoading || topicKeys.length === 0">
                <option value="" disabled>선택하세요</option>
                <option v-for="k in topicKeys" :key="k" :value="k">{{ k }}</option>
              </select>
            </label>
            <button class="btn" :disabled="!selectedTopicKey || topicClustersLoading" @click="loadTopicClusters">
              관련 클러스터 조회
            </button>
          </div>
          <p v-if="topicKeysError" class="error">{{ topicKeysError }}</p>
          <p v-else-if="topicKeysLoading" class="text-muted">키 목록 불러오는 중...</p>
          <p v-else-if="topicKeys.length === 0" class="text-muted">해당 기간/축에 데이터가 없습니다.</p>

          <p v-if="topicClustersError" class="error">{{ topicClustersError }}</p>
          <table v-else-if="selectedTopicKey" class="cluster-table">
            <thead><tr><th>대표제목</th><th>최초발생</th><th>strength</th><th>뉴스건수</th></tr></thead>
            <tbody>
              <tr v-for="c in topicClusters" :key="c.cluster_id">
                <td>{{ c.representative_title }}</td>
                <td class="mono">{{ c.first_seen_at }}</td>
                <td>{{ c.strength }}</td>
                <td>{{ c.count }}</td>
              </tr>
              <tr v-if="!topicClustersLoading && topicClusters.length === 0">
                <td colspan="4" class="text-muted">'{{ selectedTopicKey }}'와 연결된 클러스터가 없습니다.</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-if="activeSection === 'analyzed'" class="card">
          <div class="section-header">
            <h2>분석된 뉴스</h2>
            <button class="btn" :disabled="analyzedNewsLoading" @click="loadAnalyzedNews">새로고침</button>
          </div>
          <p class="text-muted hint">AI 분류가 완료된 기사 목록(최신순, 최대 100건).</p>
          <p v-if="analyzedNewsError" class="error">{{ analyzedNewsError }}</p>
          <p v-else-if="analyzedNewsLoading" class="text-muted">불러오는 중...</p>
          <table v-else class="cluster-table">
            <thead><tr><th>제목</th><th>일자</th><th>대표제목(클러스터)</th><th>strength</th><th>종목/섹터/거시</th></tr></thead>
            <tbody>
              <tr v-for="n in analyzedNews" :key="n.url_hash">
                <td>{{ n.title }}</td>
                <td class="mono">{{ n.date }}</td>
                <td>{{ n.representative_title }}</td>
                <td>{{ n.strength }}</td>
                <td>
                  <button
                    v-for="tag in newsTagRows(n)"
                    :key="`${tag.group}-${tag.key}`"
                    type="button"
                    class="tag"
                    :class="tag.group"
                    :title="`'${tag.key}' 관련 클러스터 탐색하기`"
                    @click="exploreTag(tag.key, tag.group)"
                  >
                    {{ tag.key }}
                  </button>
                  <span v-if="newsTagRows(n).length === 0" class="text-muted">-</span>
                </td>
              </tr>
              <tr v-if="analyzedNews.length === 0"><td colspan="5" class="text-muted">분석된 뉴스가 없습니다.</td></tr>
            </tbody>
          </table>
        </div>

        <div v-if="activeSection === 'pending'" class="card">
          <div class="section-header">
            <h2>
              미분석 뉴스
              <span v-if="pendingNews" class="badge">{{ pendingNews.count.toLocaleString() }}</span>
            </h2>
            <button class="btn" :disabled="pendingNewsLoading" @click="loadPendingNews">새로고침</button>
          </div>
          <p class="text-muted hint">
            크롤링은 됐지만 아직 AI 분류가 안 된 기사 목록(오래된 순, 최대 100건 표시). "뉴스
            분석 현황" 화면의 갱신 버튼으로 분류를 진행할 수 있습니다.
          </p>
          <p v-if="pendingNewsError" class="error">{{ pendingNewsError }}</p>
          <p v-else-if="pendingNewsLoading" class="text-muted">불러오는 중...</p>
          <table v-else class="cluster-table">
            <thead><tr><th>제목</th><th>수집일</th><th>URL</th></tr></thead>
            <tbody>
              <tr v-for="n in pendingNews?.items ?? []" :key="n.url_hash">
                <td>{{ n.title }}</td>
                <td class="mono">{{ n.published_at }}</td>
                <td><a :href="n.url" target="_blank" rel="noopener" class="mono">{{ n.url }}</a></td>
              </tr>
              <tr v-if="(pendingNews?.items.length ?? 0) === 0"><td colspan="3" class="text-muted">미분석 뉴스가 없습니다.</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.admin-view {
  padding: 24px;
  max-width: 1300px;
  margin: 0 auto;
  width: 100%;
  padding-bottom: 80px;
}

h1 {
  font-size: 20px;
  margin: 0 0 16px;
}

h2 {
  font-size: 15px;
  margin: 0 0 10px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.admin-layout {
  display: flex;
  align-items: flex-start;
  gap: 20px;
}

.admin-sidebar {
  flex-shrink: 0;
  width: 180px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  position: sticky;
  top: 20px;
  border-right: 1px solid var(--border);
  padding-right: 12px;
  transition: width 0.15s ease, padding-right 0.15s ease;
}

.admin-layout.sidebar-collapsed .admin-sidebar {
  width: 40px;
  padding-right: 6px;
}

.sidebar-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  border: none;
  background: transparent;
  color: var(--text-muted);
  font-size: 13px;
  font-weight: 600;
  padding: 8px 10px;
  border-radius: 4px;
  cursor: pointer;
  margin-bottom: 4px;
}

.sidebar-toggle:hover {
  background: var(--bg);
  color: var(--text);
}

.sidebar-toggle-label {
  white-space: nowrap;
}

.sidebar-item {
  text-align: left;
  border: none;
  background: transparent;
  color: var(--text-muted);
  font-size: 13.5px;
  padding: 9px 12px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}

.sidebar-item:hover {
  background: var(--bg);
  color: var(--text);
}

.sidebar-item.active {
  background: var(--accent);
  color: white;
  font-weight: 600;
}

.admin-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.card {
  border: 1px solid var(--border);
  border-radius: 4px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  padding: 18px;
  background: var(--surface);
}

.badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  border-radius: 4px;
  background: var(--accent);
  color: white;
  font-size: 11px;
  font-weight: 700;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}

.metric {
  text-align: center;
}

.metric-value {
  font-size: 20px;
  font-weight: 700;
  margin-top: 4px;
}

.metric-value.small {
  font-size: 14px;
}

.cost-note {
  font-size: 12px;
  margin: -8px 0 16px;
}

.breakdown-row {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.breakdown {
  flex: 1;
  min-width: 260px;
}

.breakdown-title {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 6px;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
}

th, td {
  text-align: left;
  padding: 5px 8px;
  border-bottom: 1px solid var(--border);
}

th {
  color: var(--text-muted);
  font-weight: 600;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}

.actions {
  display: flex;
  gap: 8px;
}

.update-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 8px;
}

.hint {
  font-size: 11.5px;
  margin: 4px 0 12px;
}

.row {
  display: flex;
  gap: 10px;
  align-items: flex-end;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.row label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
  color: var(--text-muted);
}

.row label.grow {
  flex: 1;
  min-width: 220px;
}

.cluster-table {
  margin-top: 6px;
}

.error {
  color: var(--danger);
  margin: 0 0 8px;
}

.tag {
  display: inline-block;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 1px 8px;
  margin: 0 4px 4px 0;
  font-size: 11.5px;
  cursor: pointer;
  transition: transform 0.1s ease, box-shadow 0.1s ease;
  font-family: inherit;
}

.tag:hover {
  transform: translateY(-1px);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.12);
}

/* 종목/섹터/거시경제 축 색상 — BacktestChart.vue의 종가(cyan)/뉴스신호(violet)/참고뉴스(amber)
   마커 색과 맞춰서 앱 전체에서 같은 축은 같은 색으로 인지되도록 한다. */
.tag.stock,
.axis-tile.stock {
  --axis-color: #0891b2;
}

.tag.sector,
.axis-tile.sector {
  --axis-color: #8b5cf6;
}

.tag.macro,
.axis-tile.macro {
  --axis-color: #d97706;
}

.tag.stock,
.tag.sector,
.tag.macro {
  background: color-mix(in srgb, var(--axis-color) 12%, var(--surface));
  border-color: color-mix(in srgb, var(--axis-color) 45%, transparent);
  color: var(--axis-color);
  font-weight: 600;
}

/* ---- 뉴스 분석 현황: 프레젠테이션용 요약 카드/막대그래프 ---- */

.news-card h2 {
  font-size: 19px;
}

.news-overview {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
  margin: 4px 0 18px;
}

.overview-tile {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  text-align: center;
}

.overview-tile.wide {
  grid-column: span 2;
}

.overview-label {
  font-size: 13px;
  color: var(--text-muted);
  font-weight: 600;
  margin-bottom: 6px;
}

.overview-value {
  font-size: 30px;
  font-weight: 800;
  color: var(--text);
  letter-spacing: -0.02em;
}

.overview-value.date-range {
  font-size: 17px;
  font-weight: 700;
  font-family: ui-monospace, monospace;
}

.axis-tiles {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 22px;
}

.axis-tile {
  border: 1.5px solid color-mix(in srgb, var(--axis-color) 45%, transparent);
  background: color-mix(in srgb, var(--axis-color) 8%, var(--surface));
  border-radius: 8px;
  padding: 14px 16px;
  text-align: left;
  cursor: pointer;
  transition: transform 0.12s ease, box-shadow 0.12s ease;
}

.axis-tile:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px color-mix(in srgb, var(--axis-color) 25%, transparent);
}

.axis-tile-label {
  font-size: 14px;
  font-weight: 700;
  color: var(--axis-color);
  margin-bottom: 4px;
}

.axis-tile-value {
  font-size: 26px;
  font-weight: 800;
  color: var(--text);
}

.axis-tile-hint {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 4px;
}

.strength-chart {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px 20px;
  margin-bottom: 20px;
  background: var(--surface);
}

.strength-chart-title {
  font-size: 15px;
  font-weight: 700;
  margin-bottom: 14px;
}

.strength-bars {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 10px;
  height: 140px;
}

.strength-bar-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  height: 100%;
  gap: 4px;
}

.strength-bar-track {
  flex: 1;
  width: 100%;
  max-width: 42px;
  display: flex;
  align-items: flex-end;
}

.strength-bar-fill {
  width: 100%;
  border-radius: 3px 3px 0 0;
  min-height: 0;
  transition: height 0.2s ease;
}

.strength-bar-fill.positive {
  background: var(--positive);
}

.strength-bar-fill.negative {
  background: var(--negative);
}

.strength-bar-fill.neutral {
  background: var(--text-muted);
  opacity: 0.5;
}

.strength-bar-count {
  font-size: 13px;
  font-weight: 700;
}

.strength-bar-label {
  font-size: 12px;
  color: var(--text-muted);
  font-family: ui-monospace, monospace;
}

.news-table {
  font-size: 14px;
}

.news-table th,
.news-table td {
  padding: 8px 10px;
}

@media (max-width: 900px) {
  .news-overview {
    grid-template-columns: repeat(2, 1fr);
  }

  .axis-tiles {
    grid-template-columns: 1fr;
  }
}
</style>
