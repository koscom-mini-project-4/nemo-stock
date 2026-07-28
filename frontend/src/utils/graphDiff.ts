import type { GraphEdge, GraphNode, WorkflowGraph } from '@/api/types'

export interface NodeParamDiff {
  key: string
  before: unknown
  after: unknown
}

export interface NodeDiffEntry {
  id: string
  status: 'added' | 'removed' | 'changed'
  before?: GraphNode
  after?: GraphNode
  typeChanged: boolean
  paramDiffs: NodeParamDiff[]
}

export interface EdgeDiffEntry {
  key: string
  edge: GraphEdge
  status: 'added' | 'removed'
}

export interface GraphDiff {
  nodeChanges: NodeDiffEntry[]
  edgeChanges: EdgeDiffEntry[]
  unchangedNodeCount: number
}

function edgeKey(e: GraphEdge): string {
  return `${e.from}->${e.to}${e.branch ? `:${e.branch}` : ''}`
}

function diffParams(before: Record<string, unknown>, after: Record<string, unknown>): NodeParamDiff[] {
  const keys = new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})])
  const diffs: NodeParamDiff[] = []
  for (const key of keys) {
    const beforeValue = before?.[key]
    const afterValue = after?.[key]
    if (JSON.stringify(beforeValue) !== JSON.stringify(afterValue)) {
      diffs.push({ key, before: beforeValue, after: afterValue })
    }
  }
  return diffs
}

/** AI가 제안한 워크플로 그래프를 현재 캔버스 그래프와 비교한다(전/후 비교 창용).
 * 노드는 id 기준으로 매칭하고, 파라미터가 하나라도 다르면 'changed'로 분류한다. */
export function diffGraphs(before: WorkflowGraph, after: WorkflowGraph): GraphDiff {
  const beforeMap = new Map(before.nodes.map((n) => [n.id, n]))
  const afterMap = new Map(after.nodes.map((n) => [n.id, n]))
  const ids = new Set([...beforeMap.keys(), ...afterMap.keys()])

  const nodeChanges: NodeDiffEntry[] = []
  let unchangedNodeCount = 0

  for (const id of ids) {
    const b = beforeMap.get(id)
    const a = afterMap.get(id)
    if (b && !a) {
      nodeChanges.push({ id, status: 'removed', before: b, typeChanged: false, paramDiffs: [] })
    } else if (!b && a) {
      nodeChanges.push({ id, status: 'added', after: a, typeChanged: false, paramDiffs: [] })
    } else if (b && a) {
      const typeChanged = b.type !== a.type
      const paramDiffs = diffParams(b.params ?? {}, a.params ?? {})
      if (typeChanged || paramDiffs.length > 0) {
        nodeChanges.push({ id, status: 'changed', before: b, after: a, typeChanged, paramDiffs })
      } else {
        unchangedNodeCount += 1
      }
    }
  }
  nodeChanges.sort((x, y) => x.id.localeCompare(y.id))

  const beforeEdges = new Map(before.edges.map((e) => [edgeKey(e), e]))
  const afterEdges = new Map(after.edges.map((e) => [edgeKey(e), e]))
  const edgeChanges: EdgeDiffEntry[] = []
  for (const [key, edge] of beforeEdges) {
    if (!afterEdges.has(key)) edgeChanges.push({ key, edge, status: 'removed' })
  }
  for (const [key, edge] of afterEdges) {
    if (!beforeEdges.has(key)) edgeChanges.push({ key, edge, status: 'added' })
  }

  return { nodeChanges, edgeChanges, unchangedNodeCount }
}
