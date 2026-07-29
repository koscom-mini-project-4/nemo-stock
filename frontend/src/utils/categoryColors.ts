/** 노드 카테고리별 강조색. 팔레트 아이템/캔버스 노드 외곽선에 공통으로 사용한다. */
export const CATEGORY_COLORS: Record<string, string> = {
  scheduler: '#a855f7',
  data: '#3b82f6',
  indicator: '#06b6d4',
  ai: '#ec4899',
  logic: '#f59e0b',
  risk: '#ef4444',
  execution: '#6366f1',
}

export function categoryColor(category: string | undefined): string {
  return (category && CATEGORY_COLORS[category]) || '#8b8f9a'
}
