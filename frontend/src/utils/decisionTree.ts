import type { NodeEventOut } from '@/api/types'

// TradeExplainModal.vue의 "매수/매도 근거" 타임라인을 워크플로 그래프의 실제 분기 구조(트리)로
// 보여주기 위한 순수 함수. 노드 실행은 여러 독립 분기(예: 뉴스 신호 기반 매수 분기 + IF 조건
// 기반 매도 분기)가 같은 스케줄러 노드에서 갈라져 나가는 경우가 흔한데, 기존엔 이걸 실행 순서
// 그대로 평평한 목록으로 보여줘서 서로 무관한 분기가 하나로 이어진 것처럼 보였다.

export interface DecisionStep {
  nodeId: string
  nodeType: string
  status: NodeEventOut['status']
  pass?: boolean
  reason?: string
}

export interface DecisionTreeNode {
  step: DecisionStep
  children: DecisionTreeNode[]
}

/** 최소한의 엣지 형태(from/to) — VueFlow의 Edge(source/target)와 WorkflowGraph의
 * GraphEdge(from/to)를 호출부에서 이 형태로 맞춰 넘긴다. */
export interface SimpleEdge {
  from: string
  to: string
}

/** steps(그날 실행된 노드들의 최종 상태 목록)와 워크플로 그래프의 엣지로 실행 트리를 만든다.
 * steps에 없는 노드로/노드에서 이어지는 엣지는 무시한다(이 트레이드/이 날짜에 실행되지 않은
 * 가지). 부모가 둘 이상인 노드(그래프 상 실제 합류)는 처음 만난 부모 아래에서만 렌더하고
 * 이후 등장은 건너뛴다 — 이 앱의 노드 그래프는 사이클 없는 트리/DAG이고 실제 합류는 드물어
 * 과도한 처리보다 단순함을 우선한다. edges가 비어 있거나 steps를 하나도 못 엮으면(그래프
 * 정보가 아직 없는 등) 빈 배열을 돌려주고, 호출부가 기존 평면 목록으로 폴백한다. */
export function buildDecisionTree(steps: DecisionStep[], edges: SimpleEdge[]): DecisionTreeNode[] {
  const stepById = new Map(steps.map((s) => [s.nodeId, s]))
  const childIds = new Map<string, string[]>()
  const hasParent = new Set<string>()

  for (const e of edges) {
    if (!stepById.has(e.from) || !stepById.has(e.to)) continue
    if (!childIds.has(e.from)) childIds.set(e.from, [])
    childIds.get(e.from)!.push(e.to)
    hasParent.add(e.to)
  }

  const visited = new Set<string>()
  function build(nodeId: string): DecisionTreeNode | null {
    if (visited.has(nodeId)) return null
    visited.add(nodeId)
    const step = stepById.get(nodeId)
    if (!step) return null
    const children = (childIds.get(nodeId) ?? [])
      .map(build)
      .filter((n): n is DecisionTreeNode => n !== null)
    return { step, children }
  }

  const roots = steps.filter((s) => !hasParent.has(s.nodeId))
  return roots.map((r) => build(r.nodeId)).filter((n): n is DecisionTreeNode => n !== null)
}

/** 트리 전체에서 노드 개수(펼쳐졌을 때 총 행 수) — "N개 분기" 같은 요약 표시용. */
export function countTreeNodes(nodes: DecisionTreeNode[]): number {
  let count = 0
  for (const n of nodes) count += 1 + countTreeNodes(n.children)
  return count
}
