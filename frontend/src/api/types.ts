export interface NodeParamSchema {
  key: string
  type: 'string' | 'number' | 'boolean' | 'select' | 'expression'
  label: string
  default?: unknown
  required?: boolean
  options?: string[]
}

export interface NodeTypeSchema {
  type: string
  category: string
  display_name: string
  description: string
  param_schema: NodeParamSchema[]
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

export interface WorkflowTemplateOut {
  id: string
  name: string
  description: string
  graph: WorkflowGraph
}

export interface GenerateDraftResponse {
  name: string
  graph: WorkflowGraph
  disclaimer: string
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
}

export type BacktestExplainSelection =
  | { kind: 'point'; symbol: string; date: string }
  | { kind: 'range'; symbol: string; start_date: string; end_date: string }

/** 응답 형태는 WorkflowChatResponse와 동일하다(백엔드 app/schemas/ai.py::BacktestExplainResponse 참조). */
export type BacktestExplainResponse = WorkflowChatResponse
