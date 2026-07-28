<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { chatAboutWorkflow } from '@/api/services'
import type { ChatMessage, NodeTypeSchema, WorkflowChatLastRun, WorkflowGraph } from '@/api/types'
import GraphDiffModal from '@/components/GraphDiffModal.vue'

const props = defineProps<{
  name: string
  graph: WorkflowGraph
  lastRun: WorkflowChatLastRun | null
  nodeTypes: NodeTypeSchema[]
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

const diffModalIndex = ref<number | null>(null)
const refining = ref(false)
const refineError = ref('')

function scrollToBottom() {
  nextTick(() => {
    if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight
  })
}

/** graphOverride가 있으면(다시 수정 요청) 그 그래프를 AI에게 "현재 그래프"로 제시한다 —
 * 실제 캔버스(props.graph)가 아니라 아직 적용 전인 직전 제안 위에 이어서 수정하도록 하기 위함. */
async function sendMessage(text: string, graphOverride?: WorkflowGraph) {
  const history: ChatMessage[] = messages.value.map(({ role, content }) => ({ role, content }))
  messages.value.push({ role: 'user', content: text })
  scrollToBottom()
  const result = await chatAboutWorkflow({
    name: props.name,
    graph: graphOverride ?? props.graph,
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
  scrollToBottom()
  return result
}

function extractErrorMessage(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail) return JSON.stringify(detail)
  return 'AI 응답에 실패했습니다. OPENAI_API_KEY 설정을 확인하세요.'
}

async function send() {
  const text = input.value.trim()
  if (!text || sending.value) return
  errorMessage.value = ''
  input.value = ''
  sending.value = true
  try {
    await sendMessage(text)
  } catch (err) {
    errorMessage.value = extractErrorMessage(err)
  } finally {
    sending.value = false
    scrollToBottom()
  }
}

function openDiff(idx: number) {
  refineError.value = ''
  diffModalIndex.value = idx
}

function closeDiff() {
  diffModalIndex.value = null
  refineError.value = ''
}

function confirmDiff() {
  if (diffModalIndex.value === null) return
  const msg = messages.value[diffModalIndex.value]
  if (!msg.pendingGraph) return
  emit('apply-graph', { name: msg.pendingName || props.name, graph: msg.pendingGraph })
  msg.applied = true
  closeDiff()
}

function cancelDiff() {
  if (diffModalIndex.value === null) return
  const msg = messages.value[diffModalIndex.value]
  msg.pendingGraph = undefined
  msg.pendingName = undefined
  closeDiff()
}

async function refineDiff(instruction: string) {
  if (diffModalIndex.value === null) return
  const current = messages.value[diffModalIndex.value]
  if (!current.pendingGraph) return
  refining.value = true
  refineError.value = ''
  try {
    const result = await sendMessage(instruction, current.pendingGraph)
    if (result.changed) {
      // 새 제안이 메시지 목록 끝에 추가됐다 — 비교 창을 그 제안으로 옮긴다.
      diffModalIndex.value = messages.value.length - 1
    } else {
      // AI가 그래프 변경 없이 답변만 한 경우 — 기존 제안을 그대로 유지하고 안내만 띄운다.
      refineError.value = 'AI가 그래프 변경 없이 답변했습니다. 채팅 목록에서 답변을 확인한 뒤 다시 요청해 보세요.'
    }
  } catch (err) {
    refineError.value = extractErrorMessage(err)
  } finally {
    refining.value = false
  }
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
            변경 제안 — 노드 {{ msg.pendingGraph.nodes.length }}개, 엣지 {{ msg.pendingGraph.edges.length }}개
          </div>
          <button class="btn btn-primary" type="button" @click="openDiff(idx)">비교 검토</button>
        </div>
        <div v-else-if="msg.applied" class="chat-applied text-muted">✓ 확정 적용됨</div>
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

    <GraphDiffModal
      :visible="diffModalIndex !== null"
      :before-name="name"
      :after-name="diffModalIndex !== null ? messages[diffModalIndex].pendingName || name : name"
      :before="graph"
      :after="diffModalIndex !== null ? messages[diffModalIndex].pendingGraph! : graph"
      :node-types="nodeTypes"
      :refining="refining"
      :refine-error="refineError"
      @dismiss="closeDiff"
      @confirm="confirmDiff"
      @cancel="cancelDiff"
      @refine="refineDiff"
    />
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
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.chat-pending-label {
  color: var(--text-muted);
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
