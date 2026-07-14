import { Position, type Edge as VFEdge, type Node as VFNode } from '@vue-flow/core'
import type { GraphEdge, NodeTypeSchema, WorkflowGraph } from '@/api/types'
import { computeLayeredLayout } from './layout'

export interface FlowNodeData {
  nodeType: string
  category: string
  displayName: string
  params: Record<string, unknown>
  /** 테스트 실행 애니메이션 중 상태(하이라이트용) */
  runStatus?: 'running' | 'success' | 'error' | 'skipped' | null
}

export function graphToFlowElements(
  graph: WorkflowGraph,
  nodeTypesByKey: Map<string, NodeTypeSchema>,
): { nodes: VFNode<FlowNodeData>[]; edges: VFEdge[] } {
  const positions = computeLayeredLayout(graph.nodes, graph.edges)
  const nodes: VFNode<FlowNodeData>[] = graph.nodes.map((n) => {
    const schema = nodeTypesByKey.get(n.type)
    return {
      id: n.id,
      type: 'default',
      position: positions[n.id] ?? { x: 0, y: 0 },
      label: schema?.display_name ?? n.type,
      targetPosition: Position.Left,
      sourcePosition: Position.Right,
      data: {
        nodeType: n.type,
        category: schema?.category ?? 'unknown',
        displayName: schema?.display_name ?? n.type,
        params: { ...n.params },
        runStatus: null,
      },
    }
  })
  const edges: VFEdge[] = graph.edges.map((e, i) => ({
    id: `e-${e.from}-${e.to}-${i}`,
    source: e.from,
    target: e.to,
    label: e.branch ?? undefined,
    markerEnd: 'arrowclosed' as const,
  }))
  return { nodes, edges }
}

export function flowElementsToGraph(nodes: VFNode<FlowNodeData>[], edges: VFEdge[]): WorkflowGraph {
  return {
    nodes: nodes.map((n) => ({
      id: n.id,
      type: n.data!.nodeType,
      params: n.data!.params,
    })),
    edges: edges.map(
      (e): GraphEdge => ({
        from: e.source,
        to: e.target,
        branch: typeof e.label === 'string' ? e.label : null,
      }),
    ),
  }
}
