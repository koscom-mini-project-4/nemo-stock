import type { NodeDecision, NodeEventOut } from '@/api/types'

// 필터형 노드(logic.if_else/risk.stop_loss/ai.news_signal 등)가 output_snapshot.meta.decisions
// [node_id]에 남기는 종목별 통과/탈락 판단 근거를 읽는다. ai.news_signal은 이 reason 텍스트에
// 실제로 참고한 뉴스 클러스터 제목/기여점수까지 담아둔다(app/nodes/ai/news_signal.py).
// DebugPanel.vue(전체 종목)와 TradeExplainModal.vue(특정 종목)가 공유한다.

interface DecisionsMeta {
  decisions?: Record<string, Record<string, NodeDecision>>
}

export interface DecisionRow extends NodeDecision {
  symbol: string
}

export function decisionsForEvent(evt: NodeEventOut): DecisionRow[] {
  const meta = evt.output_snapshot?.meta as DecisionsMeta | undefined
  const raw = meta?.decisions?.[evt.node_id]
  if (!raw) return []
  return Object.entries(raw).map(([symbol, decision]) => ({ symbol, ...decision }))
}

export function decisionForSymbol(evt: NodeEventOut, symbol: string): NodeDecision | null {
  const meta = evt.output_snapshot?.meta as DecisionsMeta | undefined
  return meta?.decisions?.[evt.node_id]?.[symbol] ?? null
}
