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
  created_at: string
}

export interface GenerateDraftResponse {
  name: string
  graph: WorkflowGraph
  disclaimer: string
}
