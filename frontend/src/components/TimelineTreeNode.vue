<script setup lang="ts">
import { ref } from 'vue'
import { CheckCircle2, ChevronDown, ChevronRight, GitBranch, Hourglass, SkipForward, XCircle } from '@lucide/vue'
import type { DecisionTreeNode } from '@/utils/decisionTree'
import { countTreeNodes } from '@/utils/decisionTree'

defineProps<{
  node: DecisionTreeNode
  nodeDisplayName: (nodeType: string) => string
  depth: number
}>()

// 기본은 전부 펼침(기존 평면 목록과 동일하게 처음부터 다 보임) — 분기가 많아 복잡할 때만
// 사용자가 직접 접어서 줄일 수 있게 한다("합쳐지고 줄어드는 것" 요청).
const collapsed = ref(false)

const STATUS_ICON = { running: Hourglass, success: CheckCircle2, error: XCircle, skipped: SkipForward }
</script>

<template>
  <li class="tree-node" :class="{ 'tree-node-root': depth === 0 }">
    <span v-if="depth > 0" class="tree-line-vertical" />
    <span v-if="depth > 0" class="tree-line-horizontal" />

    <div class="tree-row">
      <button
        v-if="node.children.length"
        type="button"
        class="tree-toggle"
        :aria-label="collapsed ? '펼치기' : '접기'"
        @click="collapsed = !collapsed"
      >
        <ChevronDown v-if="!collapsed" :size="13" :stroke-width="2.5" />
        <ChevronRight v-else :size="13" :stroke-width="2.5" />
      </button>
      <span v-else class="tree-toggle-spacer" />

      <span class="tree-status-icon" :class="`status-${node.step.status}`">
        <component :is="STATUS_ICON[node.step.status] ?? CheckCircle2" :size="14" :stroke-width="2.2" />
      </span>

      <span class="node-type">{{ nodeDisplayName(node.step.nodeType) }}</span>
      <span class="mono text-muted node-id">{{ node.step.nodeId }}</span>

      <span v-if="node.children.length > 1" class="branch-badge">
        <GitBranch :size="11" :stroke-width="2.2" />
        {{ node.children.length }}개 분기
      </span>

      <span v-if="node.step.pass !== undefined" :class="node.step.pass ? 'badge-pass' : 'badge-fail'">
        <CheckCircle2 v-if="node.step.pass" :size="11" :stroke-width="2.5" />
        <XCircle v-else :size="11" :stroke-width="2.5" />
        {{ node.step.pass ? '통과' : '탈락' }}
      </span>

      <span v-if="collapsed" class="text-muted collapsed-hint">
        ({{ countTreeNodes(node.children) }}개 노드 접힘)
      </span>
    </div>

    <div v-if="node.step.reason && !collapsed" class="tree-reason">{{ node.step.reason }}</div>

    <ul v-if="node.children.length && !collapsed" class="tree-children">
      <TimelineTreeNode
        v-for="child in node.children"
        :key="child.step.nodeId"
        :node="child"
        :node-display-name="nodeDisplayName"
        :depth="depth + 1"
      />
    </ul>
  </li>
</template>

<style scoped>
.tree-node {
  position: relative;
  padding-left: 24px;
}

.tree-node-root {
  padding-left: 0;
}

.tree-line-vertical {
  position: absolute;
  left: 6px;
  top: 0;
  bottom: 0;
  width: 1px;
  background: var(--border);
}

/* 마지막 형제는 분기점(가로선 높이)까지만 내려오고 아래로는 선이 이어지지 않는다 —
   git 로그 그래프처럼 가지가 실제로 끝나는 지점에서 시각적으로도 끝나게 한다. */
.tree-node:last-child > .tree-line-vertical {
  bottom: auto;
  height: 15px;
}

.tree-line-horizontal {
  position: absolute;
  left: 6px;
  top: 15px;
  width: 12px;
  height: 1px;
  background: var(--border);
}

.tree-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 0;
  flex-wrap: wrap;
  min-height: 20px;
}

.tree-toggle,
.tree-toggle-spacer {
  flex-shrink: 0;
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.tree-toggle {
  border: none;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  border-radius: 3px;
}

.tree-toggle:hover {
  background: var(--bg);
  color: var(--text);
}

.tree-status-icon {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
}

.tree-status-icon.status-running {
  color: var(--running);
}

.tree-status-icon.status-success {
  color: var(--success);
}

.tree-status-icon.status-error {
  color: var(--danger);
}

.node-type {
  font-weight: 600;
  font-size: 13px;
}

.node-id {
  font-size: 12px;
}

.branch-badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 10.5px;
  color: var(--accent);
  background: var(--accent-soft);
  border: 1px solid var(--accent-soft-border);
  padding: 1px 6px;
  border-radius: 4px;
}

.badge-pass,
.badge-fail {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--bg);
}

.badge-pass {
  color: var(--success);
}

.badge-fail {
  color: var(--danger);
}

.collapsed-hint {
  font-size: 11px;
}

.tree-reason {
  margin: 0 0 2px 24px;
  font-size: 12.5px;
  color: var(--text-muted);
  line-height: 1.5;
}

.tree-children {
  list-style: none;
  margin: 0;
  padding: 0;
}
</style>
