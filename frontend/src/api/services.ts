import { apiClient } from './client'
import type {
  BacktestResultOut,
  ChatMessage,
  GenerateDraftResponse,
  NodeTypeSchema,
  RunResultOut,
  ValidationResult,
  WorkflowChatLastRun,
  WorkflowChatResponse,
  WorkflowGraph,
  WorkflowOut,
  WorkflowStatus,
} from './types'

export async function login(username: string, password: string): Promise<string> {
  const { data } = await apiClient.post('/auth/login', { username, password })
  return data.access_token as string
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
): Promise<RunResultOut> {
  const { data } = await apiClient.post(`/workflows/${id}/run`, { overrides, universe })
  return data
}

export async function runBacktest(payload: {
  workflow_id: string
  universe: string[]
  start_date: string
  end_date: string
  initial_capital?: number
}): Promise<BacktestResultOut> {
  const { data } = await apiClient.post('/backtest', payload)
  return data
}

export async function fetchBacktest(id: string): Promise<BacktestResultOut> {
  const { data } = await apiClient.get(`/backtest/${id}`)
  return data
}

export async function generateDraft(idea: string, universe?: string[]): Promise<GenerateDraftResponse> {
  const { data } = await apiClient.post('/ai/generate-draft', { idea, universe })
  return data
}

export async function chatAboutWorkflow(payload: {
  name: string
  graph: WorkflowGraph
  message: string
  history: ChatMessage[]
  last_run?: WorkflowChatLastRun | null
}): Promise<WorkflowChatResponse> {
  const { data } = await apiClient.post('/ai/workflow-chat', payload)
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
