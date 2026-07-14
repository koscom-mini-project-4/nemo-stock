import { API_BASE_URL } from './client'
import type { NodeEventOut } from './types'

/**
 * /ws/runs/{run_id} 구독. 백엔드 InMemoryEventBus는 완료된 run의 이벤트 히스토리도
 * 보관하므로, 실행 도중이든 종료 후든 구독 시점부터 재생된다.
 *
 * 현재 전략 빌더의 "테스트 실행"은 동기 HTTP 응답(RunResultOut.events)을 받아
 * 프론트에서 타이밍을 재현하는 방식으로 디버그 하이라이트를 구현하므로 이 함수는
 * 사용하지 않는다. 활성화된 워크플로를 실시간으로 관전하는 기능(라이브 모니터링)을
 * 추가할 때 재사용할 수 있도록 유틸리티로 남겨둔다.
 */
export function subscribeRunEvents(
  runId: string,
  onEvent: (event: NodeEventOut) => void,
  onClose?: () => void,
): WebSocket {
  const wsBase = API_BASE_URL.replace(/^http/, 'ws')
  const ws = new WebSocket(`${wsBase}/ws/runs/${runId}`)
  ws.onmessage = (message) => {
    onEvent(JSON.parse(message.data) as NodeEventOut)
  }
  ws.onclose = () => onClose?.()
  return ws
}
