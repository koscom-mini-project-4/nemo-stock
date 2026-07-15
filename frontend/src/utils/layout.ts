import type { GraphEdge, GraphNode } from '@/api/types'

export interface FlowPosition {
  x: number
  y: number
}

/**
 * 스케줄러(진입점)를 기준으로 한 단순 레이어드 레이아웃.
 * 백엔드는 노드 좌표를 저장하지 않으므로(그래프 구조만 관리) 로드/구조 변경 시마다
 * 이 함수로 자동 재배치한다. 사용자가 캔버스에서 드래그한 위치는 세션 내에서만 유지된다.
 */
export function computeLayeredLayout(nodes: GraphNode[], edges: GraphEdge[]): Record<string, FlowPosition> {
  const ids = new Set(nodes.map((n) => n.id))
  const predecessors = new Map<string, string[]>()
  const successors = new Map<string, string[]>()
  nodes.forEach((n) => {
    predecessors.set(n.id, [])
    successors.set(n.id, [])
  })
  edges.forEach((e) => {
    if (ids.has(e.from) && ids.has(e.to)) {
      successors.get(e.from)?.push(e.to)
      predecessors.get(e.to)?.push(e.from)
    }
  })

  const level = new Map<string, number>()
  const queue: string[] = []
  nodes.forEach((n) => {
    if ((predecessors.get(n.id) ?? []).length === 0) {
      level.set(n.id, 0)
      queue.push(n.id)
    }
  })

  const arrivedCount = new Map<string, number>()
  let head = 0
  while (head < queue.length) {
    const cur = queue[head++]
    const curLevel = level.get(cur) ?? 0
    for (const succ of successors.get(cur) ?? []) {
      const proposed = curLevel + 1
      if (!level.has(succ) || proposed > (level.get(succ) as number)) {
        level.set(succ, proposed)
      }
      const arrived = (arrivedCount.get(succ) ?? 0) + 1
      arrivedCount.set(succ, arrived)
      if (arrived === (predecessors.get(succ) ?? []).length) {
        queue.push(succ)
      }
    }
  }
  // 사이클/고아 노드 등 도달하지 못한 노드는 0레벨로 처리(검증 오류는 별도 패널에서 안내)
  nodes.forEach((n) => {
    if (!level.has(n.id)) level.set(n.id, 0)
  })

  const byLevel = new Map<number, string[]>()
  nodes.forEach((n) => {
    const lv = level.get(n.id) as number
    if (!byLevel.has(lv)) byLevel.set(lv, [])
    byLevel.get(lv)?.push(n.id)
  })

  const positions: Record<string, FlowPosition> = {}
  // 노드 안에 파라미터 필드가 인라인으로 표시되어 기본 노드보다 커졌으므로 간격을 넉넉히 둔다.
  const xGap = 300
  const yGap = 220
  for (const [lv, levelIds] of byLevel.entries()) {
    levelIds.forEach((id, i) => {
      positions[id] = { x: lv * xGap + 40, y: i * yGap + 40 }
    })
  }
  return positions
}
