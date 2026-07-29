import { API_BASE_URL } from './client'

// POST 기반 SSE 소비 유틸(§0-18). 네이티브 EventSource는 GET 전용이라 fetch() +
// response.body.getReader()로 직접 스트림을 읽는다. 백엔드는 "data: {json}\n\n" 프레임을
// 보내며, json.type이 "chunk"(생성 중인 원문 조각)/"result"(최종 결과)/"error"(실패) 중
// 하나다.
interface SSEHandlers<T> {
  onChunk?: (text: string) => void
  onResult?: (data: T) => void
  onError?: (detail: unknown) => void
}

export async function postSSE<T = unknown>(path: string, body: unknown, handlers: SSEHandlers<T>): Promise<void> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch {
    handlers.onError?.('네트워크 오류로 요청에 실패했습니다.')
    return
  }

  if (!response.ok || !response.body) {
    let detail: unknown = `HTTP ${response.status}`
    try {
      detail = await response.json()
    } catch {
      // 응답 본문이 JSON이 아니면 상태 코드만 남긴다.
    }
    handlers.onError?.(detail)
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const frames = buffer.split('\n\n')
    buffer = frames.pop() ?? ''
    for (const frame of frames) {
      const dataLine = frame.split('\n').find((line) => line.startsWith('data: '))
      if (!dataLine) continue
      const payload = JSON.parse(dataLine.slice('data: '.length)) as { type: string; [key: string]: unknown }
      if (payload.type === 'chunk') {
        handlers.onChunk?.(payload.text as string)
      } else if (payload.type === 'result') {
        const { type: _type, ...rest } = payload
        handlers.onResult?.(rest as T)
      } else if (payload.type === 'error') {
        handlers.onError?.(payload.detail)
      }
    }
  }
}
