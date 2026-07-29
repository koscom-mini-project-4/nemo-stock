<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { postSSE } from '@/api/sse'
import { useDraftStore } from '@/stores/draft'
import type { BacktestExplainResponse, BacktestExplainSelection, ChatMessage, WorkflowGraph } from '@/api/types'

const props = defineProps<{
  backtestId: string
  workflowId: string
  selection: BacktestExplainSelection | null
}>()

const router = useRouter()
const draftStore = useDraftStore()

interface DisplayMessage extends ChatMessage {
  pendingGraph?: WorkflowGraph
  pendingName?: string
  opened?: boolean
  streaming?: boolean
}

const messages = ref<DisplayMessage[]>([])
const input = ref('')
const sending = ref(false)
const errorMessage = ref('')
const listEl = ref<HTMLDivElement | null>(null)

function selectionLabel(sel: BacktestExplainSelection): string {
  if (sel.kind === 'point') return `선택된 매매: ${sel.date} · ${sel.symbol}`
  return `선택 구간: ${sel.start_date} ~ ${sel.end_date} · ${sel.symbol}`
}

function defaultMessage(sel: BacktestExplainSelection): string {
  if (sel.kind === 'point') {
    return `이 지점(${sel.date}, ${sel.symbol})에서 왜 이런 매매가 발생했는지 설명해줘. 잘못됐다면 어떻게 고쳐야 할지도 제안해줘.`
  }
  return `이 구간(${sel.start_date} ~ ${sel.end_date}, ${sel.symbol})에서 왜 매매가 없었는지 설명해줘. 이 구간에서 매수/매도가 일어나게 하려면 로직을 어떻게 바꿔야 할지 제안해줘.`
}

watch(
  () => props.selection,
  (sel) => {
    if (sel) input.value = defaultMessage(sel)
  },
)

function scrollToBottom() {
  nextTick(() => {
    if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight
  })
}

async function send() {
  const text = input.value.trim()
  if (!text || sending.value || !props.selection) return
  errorMessage.value = ''
  const history: ChatMessage[] = messages.value.map(({ role, content }) => ({ role, content }))
  messages.value.push({ role: 'user', content: text })
  input.value = ''
  sending.value = true
  scrollToBottom()

  // 스트리밍 중(§0-18)에는 원문(JSON 파싱 전)을 이 말풍선에 그대로 누적해 보여준다.
  const assistantMsg: DisplayMessage = { role: 'assistant', content: '', streaming: true }
  messages.value.push(assistantMsg)
  scrollToBottom()

  let result: BacktestExplainResponse | null = null
  let errorDetail: unknown = null
  await postSSE<BacktestExplainResponse>(
    '/ai/backtest-explain/stream',
    { backtest_id: props.backtestId, message: text, history, selection: props.selection },
    {
      onChunk: (delta) => {
        assistantMsg.content += delta
        scrollToBottom()
      },
      onResult: (r) => {
        result = r
      },
      onError: (detail) => {
        errorDetail = detail
      },
    },
  )

  if (errorDetail || !result) {
    messages.value.pop()
    const detail = errorDetail
    errorMessage.value =
      typeof detail === 'string'
        ? detail
        : detail
          ? JSON.stringify(detail)
          : 'AI 응답에 실패했습니다. OPENAI_API_KEY 설정을 확인하세요.'
  } else {
    // onResult 콜백(클로저) 안에서만 대입되는 변수라 TS의 제어흐름 narrowing이 안 통한다.
    const finalResult = result as BacktestExplainResponse
    assistantMsg.content = finalResult.reply
    assistantMsg.streaming = false
    assistantMsg.pendingGraph = finalResult.changed ? (finalResult.graph ?? undefined) : undefined
    assistantMsg.pendingName = finalResult.changed ? (finalResult.name ?? undefined) : undefined
  }
  sending.value = false
  scrollToBottom()
}

function openInBuilder(msg: DisplayMessage) {
  if (!msg.pendingGraph) return
  draftStore.setDraft(msg.pendingName || '백테스트 AI 제안', msg.pendingGraph, props.workflowId)
  msg.opened = true
  router.push(`/strategies/${props.workflowId}`)
}

function discardPending(msg: DisplayMessage) {
  msg.pendingGraph = undefined
  msg.pendingName = undefined
}
</script>

<template>
  <div class="ask-panel">
    <div v-if="selection" class="selection-banner">{{ selectionLabel(selection) }}</div>
    <div ref="listEl" class="chat-list">
      <p v-if="messages.length === 0" class="text-muted chat-empty">
        차트에서 매매 지점(▲/▼)을 클릭하거나, 매매가 없는 구간을 드래그해 선택하면 이 전략의 로직을
        근거로 AI에게 물어볼 수 있습니다.
      </p>
      <div v-for="(msg, idx) in messages" :key="idx" :class="['chat-msg', `chat-msg-${msg.role}`]">
        <div class="chat-bubble" :class="{ 'chat-bubble-streaming': msg.streaming }">{{ msg.content }}</div>
        <div v-if="msg.streaming" class="text-muted chat-typing">AI가 작성 중...</div>
        <div v-if="msg.pendingGraph && !msg.opened" class="chat-pending">
          <div class="chat-pending-label">
            수정 제안 — 노드 {{ msg.pendingGraph.nodes.length }}개, 엣지 {{ msg.pendingGraph.edges.length }}개
          </div>
          <div class="chat-pending-actions">
            <button class="btn btn-primary" type="button" @click="openInBuilder(msg)">전략 빌더에서 열기</button>
            <button class="btn" type="button" @click="discardPending(msg)">닫기</button>
          </div>
        </div>
        <div v-else-if="msg.opened" class="chat-applied text-muted">✓ 전략 빌더로 이동해 확인하세요</div>
      </div>
    </div>
    <p v-if="errorMessage" class="error chat-error">{{ errorMessage }}</p>
    <div class="chat-input-row">
      <input
        v-model="input"
        type="text"
        :placeholder="selection ? '질문을 확인/수정 후 전송하세요' : '차트에서 매매 지점이나 구간을 먼저 선택하세요'"
        :disabled="sending || !selection"
        @keydown.enter="send"
      />
      <button class="btn btn-primary" type="button" :disabled="sending || !selection || !input.trim()" @click="send">
        전송
      </button>
    </div>
  </div>
</template>

<style scoped>
.ask-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: 10px;
  gap: 8px;
}

.selection-banner {
  font-size: 12px;
  padding: 6px 8px;
  border-radius: 6px;
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text-muted);
  flex-shrink: 0;
}

.chat-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.chat-empty {
  font-size: 13px;
  line-height: 1.5;
}

.chat-msg {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.chat-msg-user {
  align-items: flex-end;
}

.chat-msg-assistant {
  align-items: flex-start;
}

.chat-bubble {
  max-width: 92%;
  padding: 8px 10px;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
}

.chat-msg-user .chat-bubble {
  background: var(--accent);
  color: white;
  border-bottom-right-radius: 2px;
}

.chat-msg-assistant .chat-bubble {
  background: var(--surface);
  border: 1px solid var(--border);
  border-bottom-left-radius: 2px;
}

.chat-bubble-streaming {
  font-family: ui-monospace, monospace;
  font-size: 11.5px;
  color: var(--text-muted);
}

.chat-pending {
  border: 1px solid var(--accent);
  border-radius: 6px;
  padding: 8px;
  font-size: 12.5px;
  width: 100%;
}

.chat-pending-label {
  margin-bottom: 6px;
  color: var(--text-muted);
}

.chat-pending-actions {
  display: flex;
  gap: 6px;
}

.chat-applied {
  font-size: 12px;
}

.chat-typing {
  font-size: 12px;
  margin: 0;
}

.chat-error {
  margin: 0;
  font-size: 12px;
}

.chat-input-row {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

.chat-input-row input {
  flex: 1;
}
</style>
