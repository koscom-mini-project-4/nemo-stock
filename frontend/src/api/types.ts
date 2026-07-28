export interface NodeParamSchema {
  key: string
  type: 'string' | 'number' | 'boolean' | 'select' | 'expression' | 'prompt'
  label: string
  default?: unknown
  required?: boolean
  options?: string[]
  /** options와 같은 길이의 사람이 읽는 라벨(매매 조건 프리셋 표시용) */
  option_labels?: string[]
  /** 프론트 입력 그룹: 'calc'(계산용 파라미터) | 'condition'(매매 조건) */
  group?: 'calc' | 'condition'
  /** 입력 도움말(예: "5, 20, 60, 120") */
  hint?: string
  /** {param, equals}일 때만 노출(예: '직접 설정' 선택 시에만 연산자/기준값 노출) */
  show_if?: { param: string; equals: string }
}

export interface NodeTypeSchema {
  type: string
  category: string
  /** 분류(예: 추세/모멘텀/변동성/거래량) — 팔레트 2차 그룹핑용 */
  subcategory?: string
  display_name: string
  description: string
  /** 매매 신호 발생 예시 */
  example?: string
  param_schema: NodeParamSchema[]
}

/** 필터형 노드(logic.if_else/logic.rank/risk.stop_loss/조건 내장 지표 노드)의 종목별 판단 근거.
 * NodeEventOut.output_snapshot.meta.decisions[node_id][symbol]에서 읽는다. */
export interface NodeDecision {
  pass: boolean
  reason: string
  metrics?: Record<string, unknown>
}

export interface GraphNode {
  id: string
  type: string
  params: Record<string, unknown>
}

export interface GraphEdge {
  from: string
  to: string
  branch?: string | null
}

export interface WorkflowGraph {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export type WorkflowStatus = 'draft' | 'active' | 'inactive'

export interface WorkflowOut {
  id: string
  user_id: string
  name: string
  graph: WorkflowGraph
  status: WorkflowStatus
  schedule_interval_sec: number
  created_at: string
  updated_at: string
}

export interface ValidationResult {
  valid: boolean
  errors: string[]
  execution_order: string[]
}

export type NodeEventStatus = 'running' | 'success' | 'error' | 'skipped'

export interface NodeEventOut {
  node_id: string
  node_type: string
  status: NodeEventStatus
  timestamp: string
  input_snapshot?: Record<string, unknown> | null
  output_snapshot?: Record<string, unknown> | null
  error?: string | null
  duration_ms?: number | null
}

export interface RunResultOut {
  run_id: string
  workflow_id: string
  mode: string
  status: string
  started_at: string
  finished_at: string
  error?: string | null
  events: NodeEventOut[]
  final_symbols: Record<string, Record<string, unknown>>
}

export interface EquityPoint {
  date: string
  equity: number
}

export interface DailyRunOut {
  date: string
  run_id: string
}

export interface TradeOut {
  date: string
  run_id: string
  order_id: string
  symbol: string
  side: 'buy' | 'sell'
  qty: number
  price: number
  status: string
  reason?: string | null
  realized_pnl?: number | null
}

export interface PricePointOut {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface NewsMarkerOut {
  date: string
  news_id: string
  title: string
  published_at: string
  source: string
  used: boolean
}

export interface BacktestResultOut {
  id: string
  workflow_id: string
  start_date: string
  end_date: string
  initial_capital: number
  final_equity: number
  total_return_pct: number
  cagr_pct: number
  mdd_pct: number
  volatility_pct: number
  win_rate_pct: number
  profit_loss_ratio: number | null
  trade_count: number
  equity_curve: EquityPoint[]
  daily_runs: DailyRunOut[]
  universe: string[]
  trades: TradeOut[]
  created_at: string
}

export interface PositionOut {
  symbol: string
  qty: number
  avg_price: number
}

export interface AccountSummaryOut {
  cash: number
  equity: number
  positions: PositionOut[]
}

export interface SymbolOut {
  symbol: string
  name: string
}

export interface WorkflowTemplateOut {
  id: string
  name: string
  description: string
  graph: WorkflowGraph
}

/** 이 호출 1건에서 새로 쌓인 AI 토큰 사용량(§0-11). usage_repo 미기록 시 null일 수 있다. */
export interface AIUsageDelta {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
}

export interface GenerateDraftResponse {
  name: string
  graph: WorkflowGraph
  disclaimer: string
  usage?: AIUsageDelta | null
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface WorkflowChatLastRun {
  status: string
  events: NodeEventOut[]
  final_symbols: Record<string, Record<string, unknown>>
}

export interface WorkflowChatResponse {
  reply: string
  changed: boolean
  name?: string | null
  graph?: WorkflowGraph | null
  disclaimer?: string | null
  usage?: AIUsageDelta | null
}

export type BacktestExplainSelection =
  | { kind: 'point'; symbol: string; date: string }
  | { kind: 'range'; symbol: string; start_date: string; end_date: string }

/** 응답 형태는 WorkflowChatResponse와 동일하다(백엔드 app/schemas/ai.py::BacktestExplainResponse 참조). */
export type BacktestExplainResponse = WorkflowChatResponse

// --- 관리자 페이지(GET /admin/metrics, /data/news/{stats,clusters,update}) ---

export interface AIUsageByBreakdown {
  purpose?: string
  model?: string
  calls: number
  total_tokens: number
}

export interface AIUsageSummary {
  total_calls: number
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  by_purpose: AIUsageByBreakdown[]
  by_model: AIUsageByBreakdown[]
}

export interface AdminMetrics {
  backtest_count: number
  ai_usage: AIUsageSummary
}

/** NewsTrader.stats()/clusters()를 그대로 통과시키는 응답이라 키가 한글이다(라이브러리
 * 원본 스키마, app/vendor/news_classifier). 고정 스키마를 강제하지 않고 느슨하게 받는다. */
export type NewsStats = Record<string, unknown>

export interface NewsCluster {
  id: number
  representative_title: string
  first_seen_at: string
  strength: number
  news_count: number
  /** 이 클러스터(주제)에 연결된 종목/섹터/거시지표 키(§0-7, 관리자 페이지 상호 탐색용). */
  종목?: string[]
  섹터?: string[]
  거시지표?: string[]
}

/** GET /data/news/pending(§0-12) 항목 — 크롤링은 됐지만 아직 AI 분류가 안 된 기사. */
export interface PendingNewsItem {
  url_hash: string
  url: string
  title: string
  published_at: string
}

export interface PendingNewsResult {
  count: number
  items: PendingNewsItem[]
}

/** GET /data/news/analyzed(§0-12) 항목 — 이미 AI 분류된 기사 1건(여러 종목/섹터가 걸려도
 * url_hash 기준으로 한 행으로 접힘). */
export interface AnalyzedNewsItem {
  url_hash: string
  title: string
  date: string
  cluster_id: number
  representative_title: string
  strength: number
  stocks: string[]
  sectors: string[]
  macros: string[]
}

/** GET /data/news/topics(-/clusters)의 axis 값. app/nodes/ai/news_signal.py의 AXIS_METHOD와 동일 매핑. */
export type NewsTopicGroup = 'stock' | 'sector' | 'macro'

/** 특정 종목/섹터/거시지표 키로부터 역탐색한 클러스터 — NewsCluster와 필드명이 다르다
 * (백엔드가 NewsTrader.clusters_for_key()를 그대로 통과시킴, `id`가 아니라 `cluster_id`). */
export interface NewsTopicCluster {
  cluster_id: number
  representative_title: string
  first_seen_at: string
  strength: number
  count: number
}

export interface NewsUpdateResult {
  skipped: boolean
  collected?: number | null
  classified?: number | null
  pending?: number | null
  purged_clusters?: number | null
  minutes_since_last_update?: number | null
}

/** GET /data/symbols/stats(§0-10) — count는 현재 캐시(동기화 전이면 8개 폴백 시드),
 * db_count는 sqlite에 저장된(직전 동기화) 건수. */
export interface SymbolStats {
  count: number
  db_count: number
}

export interface SymbolSyncResult {
  synced: number
  as_of: string
  /** 'data.go.kr'(공공데이터포털, 무료) | 'koscom'(CHECK-API, 공공데이터 응답이 비었을 때 폴백) */
  source: string
}
