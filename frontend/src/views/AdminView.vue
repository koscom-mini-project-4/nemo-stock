<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import {
  fetchAdminMetrics,
  fetchNewsClusters,
  fetchNewsStats,
  fetchNewsTopicClusters,
  fetchNewsTopicKeys,
  fetchSymbolStats,
  syncSymbols,
  triggerNewsUpdate,
} from '@/api/services'
import type {
  AdminMetrics,
  NewsCluster,
  NewsStats,
  NewsTopicCluster,
  NewsTopicGroup,
  NewsUpdateResult,
  SymbolStats,
} from '@/api/types'

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

function clusterTags(c: NewsCluster): string[] {
  return [...(c.종목 ?? []), ...(c.섹터 ?? []), ...(c.거시지표 ?? [])]
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

watch(topicGroup, loadTopicKeys)

async function runUpdate(force: boolean) {
  updating.value = true
  updateError.value = ''
  updateResult.value = null
  try {
    updateResult.value = await triggerNewsUpdate(force)
    // 갱신 후 현황도 같이 새로고침한다.
    await Promise.all([loadNewsStats(), loadClusters()])
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
})
</script>

<template>
  <div class="admin-view">
    <h1>관리자</h1>

    <div class="card">
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
        </div>

        <div class="breakdown-row">
          <div class="breakdown">
            <div class="breakdown-title">목적별</div>
            <table>
              <thead><tr><th>purpose</th><th>호출</th><th>토큰</th></tr></thead>
              <tbody>
                <tr v-for="b in metrics.ai_usage.by_purpose" :key="b.purpose">
                  <td class="mono">{{ b.purpose }}</td>
                  <td>{{ b.calls }}</td>
                  <td>{{ b.total_tokens.toLocaleString() }}</td>
                </tr>
                <tr v-if="metrics.ai_usage.by_purpose.length === 0"><td colspan="3" class="text-muted">기록 없음</td></tr>
              </tbody>
            </table>
          </div>
          <div class="breakdown">
            <div class="breakdown-title">모델별</div>
            <table>
              <thead><tr><th>model</th><th>호출</th><th>토큰</th></tr></thead>
              <tbody>
                <tr v-for="b in metrics.ai_usage.by_model" :key="b.model">
                  <td class="mono">{{ b.model }}</td>
                  <td>{{ b.calls }}</td>
                  <td>{{ b.total_tokens.toLocaleString() }}</td>
                </tr>
                <tr v-if="metrics.ai_usage.by_model.length === 0"><td colspan="3" class="text-muted">기록 없음</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </template>
    </div>

    <div class="card">
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
        자동 매핑이 위 뉴스 분석 현황 검색과 같은 기준으로 훨씬 많은 종목에서 동작합니다.
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

    <div class="card">
      <div class="section-header">
        <h2>뉴스 분석 현황</h2>
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
        갱신은 즉시 크롤링+AI 분류를 트리거합니다(수 분 소요될 수 있음).
      </p>

      <p v-if="newsStatsError" class="error">{{ newsStatsError }}</p>
      <p v-else-if="newsStatsLoading" class="text-muted">불러오는 중...</p>
      <pre v-else-if="newsStats" class="mono stats-json">{{ JSON.stringify(newsStats, null, 2) }}</pre>

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
      <table v-else class="cluster-table">
        <thead><tr><th>대표제목</th><th>최초발생</th><th>strength</th><th>뉴스건수</th><th>관련 종목/섹터/거시</th></tr></thead>
        <tbody>
          <tr v-for="c in clusters" :key="c.id">
            <td>{{ c.representative_title }}</td>
            <td class="mono">{{ c.first_seen_at }}</td>
            <td>{{ c.strength }}</td>
            <td>{{ c.news_count }}</td>
            <td>
              <span v-for="tag in clusterTags(c)" :key="tag" class="tag">{{ tag }}</span>
              <span v-if="clusterTags(c).length === 0" class="text-muted">-</span>
            </td>
          </tr>
          <tr v-if="!clustersLoading && clusters.length === 0"><td colspan="5" class="text-muted">해당 기간에 클러스터가 없습니다.</td></tr>
        </tbody>
      </table>
    </div>

    <div class="card">
      <h2>종목/섹터/거시로 클러스터 탐색</h2>
      <p class="text-muted hint">
        위 뉴스 분석 현황의 기간({{ clusterStart }} ~ {{ clusterEnd }})을 그대로 사용합니다. 기간을
        바꾸려면 위 조회란을 먼저 갱신하세요.
      </p>
      <div class="row">
        <label>
          축
          <select v-model="topicGroup">
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
  </div>
</template>

<style scoped>
.admin-view {
  padding: 24px;
  max-width: 1100px;
  margin: 0 auto;
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

h1 {
  font-size: 20px;
  margin: 0 0 12px;
}

h2 {
  font-size: 15px;
  margin: 0 0 10px;
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

.hint {
  font-size: 11.5px;
  margin: 4px 0 12px;
}

.stats-json {
  background: var(--bg);
  padding: 10px;
  border-radius: 6px;
  max-height: 220px;
  overflow: auto;
  font-size: 12px;
  margin: 0 0 16px;
}

.row {
  display: flex;
  gap: 10px;
  align-items: flex-end;
  margin-bottom: 10px;
}

.row label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
  color: var(--text-muted);
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
  border-radius: 10px;
  padding: 1px 8px;
  margin: 0 4px 4px 0;
  font-size: 11.5px;
}
</style>
