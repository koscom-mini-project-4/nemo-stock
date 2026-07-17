<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { chatAboutWorkflow } from '@/api/services'
import type { ChatMessage, WorkflowChatLastRun, WorkflowGraph } from '@/api/types'

const props = defineProps<{
  name: string
  graph: WorkflowGraph
  lastRun: WorkflowChatLastRun | null
}>()

const emit = defineEmits<{
  'apply-graph': [payload: { name: string; graph: WorkflowGraph }]
}>()

interface DisplayMessage extends ChatMessage {
  pendingGraph?: WorkflowGraph
  pendingName?: string
  applied?: boolean
}

const messages = ref<DisplayMessage[]>([])
const input = ref('')
const sending = ref(false)
const errorMessage = ref('')
const listEl = ref<HTMLDivElement | null>(null)

function scrollToBottom() {
  nextTick(() => {
    if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight
  })
}

async function send() {
  const text = input.value.trim()
  if (!text || sending.value) return
  errorMessage.value = ''
  const history: ChatMessage[] = messages.value.map(({ role, content }) => ({ role, content }))
  messages.value.push({ role: 'user', content: text })
  input.value = ''
  sending.value = true
  scrollToBottom()
  try {
    const result = await chatAboutWorkflow({
      name: props.name,
      graph: props.graph,
      message: text,
      history,
      last_run: props.lastRun,
    })
    messages.value.push({
      role: 'assistant',
      content: result.reply,
      pendingGraph: result.changed ? (result.graph ?? undefined) : undefined,
      pendingName: result.changed ? (result.name ?? undefined) : undefined,
    })
  } catch (err) {
    const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
    errorMessage.value =
      typeof detail === 'string'
        ? detail
        : detail
          ? JSON.stringify(detail)
          : 'AI 응답에 실패했습니다. OPENAI_API_KEY 설정을 확인하세요.'
  } finally {
    sending.value = false
    scrollToBottom()
  }
}

function applyPending(msg: DisplayMessage) {
  if (!msg.pendingGraph) return
  emit('apply-graph', { name: msg.pendingName || props.name, graph: msg.pendingGraph })
  msg.applied = true
}

function discardPending(msg: DisplayMessage) {
  msg.pendingGraph = undefined
  msg.pendingName = undefined
}
</script>

<template>
  <div class="chat-panel">
    <div ref="listEl" class="chat-list">
      <p v-if="messages.length === 0" class="text-muted chat-empty">
        노드 수정을 지시하거나(예: "손절 5%로 바꿔줘"), 현재 전략/실행 결과에 대해 물어보세요(예: "이
        전략은 지금 뭘 하는거야?").
      </p>
      <div v-for="(msg, idx) in messages" :key="idx" :class="['chat-msg', `chat-msg-${msg.role}`]">
        <div class="chat-bubble">{{ msg.content }}</div>
        <div v-if="msg.pendingGraph && !msg.applied" class="chat-pending">
          <div class="chat-pending-label">
            변경 미리보기 — 노드 {{ msg.pendingGraph.nodes.length }}개, 엣지 {{ msg.pendingGraph.edges.length }}개
          </div>
          <div class="chat-pending-actions">
            <button class="btn btn-primary" type="button" @click="applyPending(msg)">적용</button>
            <button class="btn" type="button" @click="discardPending(msg)">취소</button>
          </div>
        </div>
        <div v-else-if="msg.applied" class="chat-applied text-muted">✓ 캔버스에 적용됨</div>
      </div>
      <p v-if="sending" class="text-muted chat-typing">AI가 응답 중...</p>
    </div>
    <p v-if="errorMessage" class="error chat-error">{{ errorMessage }}</p>
    <div class="chat-input-row">
      <input
        v-model="input"
        type="text"
        placeholder="예) 손절 5%로 바꿔줘 / 지금 이 전략 뭐하는거야?"
        :disabled="sending"
        @keydown.enter="send"
      />
      <button class="btn btn-primary" type="button" :disabled="sending || !input.trim()" @click="send">전송</button>
    </div>
  </div>
</template>

<style scoped>
.chat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: 10px;
  gap: 8px;
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
