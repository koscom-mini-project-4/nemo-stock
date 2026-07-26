import { defineStore } from 'pinia'
import type { WorkflowGraph } from '@/api/types'

interface PendingDraft {
  name: string
  graph: WorkflowGraph
  /** 지정되면 그 workflowId로 빌더를 열 때만(기존 워크플로 편집 화면) 적용된다.
   * 없으면(AI 전략 생성 -> 신규 작성) 기존처럼 /strategies/new 진입 시 적용된다. */
  targetWorkflowId?: string
}

/** AI 전략 생성/백테스트 결과 화면 -> 전략 빌더 화면으로 초안을 전달하기 위한 임시 저장소(세션 내 1회성). */
export const useDraftStore = defineStore('draft', {
  state: () => ({
    pending: null as PendingDraft | null,
  }),
  actions: {
    setDraft(name: string, graph: WorkflowGraph, targetWorkflowId?: string) {
      this.pending = { name, graph, targetWorkflowId }
    },
    consumeDraft() {
      const draft = this.pending
      this.pending = null
      return draft
    },
  },
})
