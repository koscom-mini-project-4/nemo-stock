import { apiClient } from './client'
import type {
  AccountSummaryOut,
  AdminMetrics,
  AnalyzedNewsItem,
  BacktestExplainResponse,
  BacktestExplainSelection,
  BacktestResultOut,
  ChatMessage,
  NewsCluster,
  NewsMarkerOut,
  NewsStats,
  NewsTopicCluster,
  NewsTopicGroup,
  NewsUpdateResult,
  NodeTypeSchema,
  PendingNewsResult,
  PositionOut,
  PricePointOut,
  RunResultOut,
  SymbolOut,
  SymbolStats,
  SymbolSyncResult,
  ValidationResult,
  WatchlistItemOut,
  WorkflowGraph,
  WorkflowOut,
  WorkflowPnlOut,
  WorkflowStatus,
  WorkflowTemplateOut,
} from './types'

export async function fetchAccountSummary(): Promise<AccountSummaryOut> {
  const { data } = await apiClient.get('/account/summary')
  return data
}

export async function upsertPosition(symbol: string, qty: number, avgPrice: number): Promise<PositionOut> {
  const { data } = await apiClient.put(`/account/positions/${symbol}`, { qty, avg_price: avgPrice })
  return data
}

export async function deletePosition(symbol: string): Promise<void> {
  await apiClient.delete(`/account/positions/${symbol}`)
}

export async function fetchWatchlist(): Promise<WatchlistItemOut[]> {
  const { data } = await apiClient.get('/account/watchlist')
  return data
}

export async function addWatchlistItem(symbol: string): Promise<WatchlistItemOut[]> {
  const { data } = await apiClient.post('/account/watchlist', { symbol })
  return data
}

export async function removeWatchlistItem(symbol: string): Promise<void> {
  await apiClient.delete(`/account/watchlist/${symbol}`)
}

export async function fetchPrices(symbol: string, days = 180): Promise<PricePointOut[]> {
  const { data } = await apiClient.get(`/data/prices/${symbol}`, { params: { days } })
  return data
}

export async function fetchSymbols(q = ''): Promise<SymbolOut[]> {
  const { data } = await apiClient.get('/data/symbols', { params: q ? { q } : undefined })
  return data
}

export async function fetchWorkflowTemplates(): Promise<WorkflowTemplateOut[]> {
  const { data } = await apiClient.get('/workflows/templates')
  return data
}

export async function fetchNodeTypes(): Promise<NodeTypeSchema[]> {
  const { data } = await apiClient.get('/nodes')
  return data
}

export async function fetchWorkflows(): Promise<WorkflowOut[]> {
  const { data } = await apiClient.get('/workflows')
  return data
}

export async function fetchWorkflow(id: string): Promise<WorkflowOut> {
  const { data } = await apiClient.get(`/workflows/${id}`)
  return data
}

export async function fetchWorkflowPnlSummary(): Promise<WorkflowPnlOut[]> {
  const { data } = await apiClient.get('/workflows/pnl-summary')
  return data
}

export async function createWorkflow(
  name: string,
  graph: WorkflowGraph,
  scheduleIntervalSec: number,
): Promise<WorkflowOut> {
  const { data } = await apiClient.post('/workflows', {
    name,
    graph,
    schedule_interval_sec: scheduleIntervalSec,
  })
  return data
}

export async function updateWorkflow(
  id: string,
  payload: Partial<{ name: string; graph: WorkflowGraph; schedule_interval_sec: number; status: WorkflowStatus }>,
): Promise<WorkflowOut> {
  const { data } = await apiClient.put(`/workflows/${id}`, payload)
  return data
}

export async function deleteWorkflow(id: string): Promise<void> {
  await apiClient.delete(`/workflows/${id}`)
}

export async function validateWorkflow(id: string): Promise<ValidationResult> {
  const { data } = await apiClient.post(`/workflows/${id}/validate`)
  return data
}

export async function runWorkflow(
  id: string,
  overrides: Record<string, Record<string, Record<string, unknown>>>,
  universe?: string[],
  targetNodeId?: string,
): Promise<RunResultOut> {
  const { data } = await apiClient.post(`/workflows/${id}/run`, {
    overrides,
    universe,
    target_node_id: targetNodeId,
  })
  return data
}

export async function runBacktest(payload: {
  workflow_id: string
  universe: string[]
  start_date: string
  end_date: string
  initial_capital?: number
  progress_run_id?: string
}): Promise<BacktestResultOut> {
  const { data } = await apiClient.post('/backtest', payload)
  return data
}

export async function fetchBacktest(id: string): Promise<BacktestResultOut> {
  const { data } = await apiClient.get(`/backtest/${id}`)
  return data
}

export async function fetchRun(workflowId: string, runId: string): Promise<RunResultOut> {
  const { data } = await apiClient.get(`/workflows/${workflowId}/runs/${runId}`)
  return data
}

export async function fetchBacktestPrices(
  id: string,
  symbol: string,
  interval: 'day' | 'minute60' = 'day',
): Promise<PricePointOut[]> {
  const { data } = await apiClient.get(`/backtest/${id}/prices`, { params: { symbol, interval } })
  return data
}

export async function fetchBacktestNewsUsed(id: string, symbol: string): Promise<NewsMarkerOut[]> {
  const { data } = await apiClient.get(`/backtest/${id}/news/used`, { params: { symbol } })
  return data
}

export async function fetchBacktestNewsAll(id: string, symbol: string): Promise<NewsMarkerOut[]> {
  const { data } = await apiClient.get(`/backtest/${id}/news/all`, { params: { symbol } })
  return data
}

export async function fetchBacktestNewsSignal(id: string, symbol: string): Promise<NewsMarkerOut[]> {
  const { data } = await apiClient.get(`/backtest/${id}/news/signal`, { params: { symbol } })
  return data
}

export async function explainBacktest(payload: {
  backtest_id: string
  message: string
  history: ChatMessage[]
  selection: BacktestExplainSelection
}): Promise<BacktestExplainResponse> {
  const { data } = await apiClient.post('/ai/backtest-explain', payload)
  return data
}

export interface ManualPriceBar {
  trade_date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export async function ingestManualPrices(symbol: string, bars: ManualPriceBar[]): Promise<{ ingested: number }> {
  const { data } = await apiClient.post('/data/ingest/prices/manual', { symbol, bars })
  return data
}

export async function fetchAdminMetrics(): Promise<AdminMetrics> {
  const { data } = await apiClient.get('/admin/metrics')
  return data
}

export async function fetchNewsStats(): Promise<NewsStats> {
  const { data } = await apiClient.get('/data/news/stats')
  return data
}

export async function fetchNewsClusters(start: string, end: string): Promise<NewsCluster[]> {
  const { data } = await apiClient.get('/data/news/clusters', { params: { start, end } })
  return data
}

export async function triggerNewsUpdate(
  force = false,
  options?: { days?: number; keywords?: string[] },
): Promise<NewsUpdateResult> {
  const { data } = await apiClient.post('/data/news/update', {
    force,
    days: options?.days,
    keywords: options?.keywords,
  })
  return data
}

export async function fetchNewsPending(limit = 100): Promise<PendingNewsResult> {
  const { data } = await apiClient.get('/data/news/pending', { params: { limit } })
  return data
}

export async function fetchNewsAnalyzed(limit = 100): Promise<AnalyzedNewsItem[]> {
  const { data } = await apiClient.get('/data/news/analyzed', { params: { limit } })
  return data
}

export async function fetchNewsTopicKeys(group: NewsTopicGroup, start: string, end: string): Promise<string[]> {
  const { data } = await apiClient.get('/data/news/topics', { params: { group, start, end } })
  return data
}

export async function fetchNewsTopicClusters(
  group: NewsTopicGroup,
  key: string,
  start: string,
  end: string,
): Promise<NewsTopicCluster[]> {
  const { data } = await apiClient.get('/data/news/topics/clusters', { params: { group, key, start, end } })
  return data
}

export async function fetchSymbolStats(): Promise<SymbolStats> {
  const { data } = await apiClient.get('/data/symbols/stats')
  return data
}

export async function syncSymbols(): Promise<SymbolSyncResult> {
  const { data } = await apiClient.post('/data/symbols/sync')
  return data
}
