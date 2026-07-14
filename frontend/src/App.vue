<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const showNav = computed(() => route.name !== 'login')

function logout() {
  auth.logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <div class="app-shell">
    <header v-if="showNav" class="app-header">
      <div class="brand">
        <RouterLink to="/">네모네모매매</RouterLink>
        <span class="text-muted">nemo-stock PoC</span>
      </div>
      <nav>
        <RouterLink to="/" class="nav-link">대시보드</RouterLink>
        <RouterLink to="/strategies/new" class="nav-link">새 전략</RouterLink>
        <RouterLink to="/ai/generate" class="nav-link">AI 전략 생성</RouterLink>
      </nav>
      <button class="btn" @click="logout">로그아웃</button>
    </header>
    <main class="app-main">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.app-header {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 10px 20px;
  border-bottom: 1px solid var(--border);
  background: var(--surface);
}

.brand {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-weight: 700;
}

.brand a {
  color: var(--text);
  text-decoration: none;
}

nav {
  display: flex;
  gap: 4px;
  flex: 1;
}

.nav-link {
  padding: 6px 10px;
  border-radius: 6px;
  color: var(--text-muted);
  text-decoration: none;
  font-size: 14px;
}

.nav-link:hover,
.nav-link.router-link-exact-active {
  background: var(--bg);
  color: var(--text);
}

.app-main {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
</style>
