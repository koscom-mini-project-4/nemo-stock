/** 백엔드가 내려주는 영문 상태값을 화면에 표시할 한글 라벨로 바꾼다. */

const WORKFLOW_STATUS_LABELS: Record<string, string> = {
  draft: '초안',
  active: '실행 중',
  inactive: '중지',
}

export function workflowStatusLabel(status: string): string {
  return WORKFLOW_STATUS_LABELS[status] ?? status
}

const TRADE_STATUS_LABELS: Record<string, string> = {
  filled: '체결',
  rejected: '거절',
}

export function tradeStatusLabel(status: string): string {
  return TRADE_STATUS_LABELS[status] ?? status
}
