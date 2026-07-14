import { defineStore } from 'pinia'
import type { WorkflowGraph } from '@/api/types'

/** AI 전략 생성 화면 -> 전략 빌더 화면으로 초안을 전달하기 위한 임시 저장소(세션 내 1회성). */
export const useDraftStore = defineStore('draft', {
  state: () => ({
    pending: null as { name: string; graph: WorkflowGraph } | null,
  }),
  actions: {
    setDraft(name: string, graph: WorkflowGraph) {
      this.pending = { name, graph }
    },
    consumeDraft() {
      const draft = this.pending
      this.pending = null
      return draft
    },
  },
})
