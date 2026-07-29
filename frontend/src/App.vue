<script setup lang="ts"></script>

<template>
  <div class="app-shell">
    <header class="app-header">
      <RouterLink to="/" class="brand">
        <img src="/logo.png" alt="" class="brand-logo" />
        <span class="brand-name">네모네모매매</span>
      </RouterLink>
      <nav>
        <RouterLink to="/" class="nav-link">대시보드</RouterLink>
        <RouterLink to="/strategies/new" class="nav-link">새 전략</RouterLink>
        <RouterLink to="/admin" class="nav-link">관리자</RouterLink>
      </nav>
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
  gap: 28px;
  padding: 12px clamp(16px, 3vw, 32px);
  border-bottom: 1px solid var(--border);
  background: var(--surface);
  box-shadow: 0 2px 10px rgba(19, 43, 83, 0.06);
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-strong);
  text-decoration: none;
}

.brand-logo {
  height: 32px;
  width: auto;
  display: block;
}

.brand-name {
  font-size: 22px;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: var(--text-strong);
}

nav {
  display: flex;
  gap: 6px;
  flex: 1;
}

.nav-link {
  padding: 8px 12px;
  border-radius: 3px;
  border-bottom: 2px solid transparent;
  color: var(--text-muted);
  text-decoration: none;
  font-size: 14px;
  font-weight: 600;
  transition: color 0.15s, border-color 0.15s;
}

.nav-link:hover {
  color: var(--text);
}

.nav-link.router-link-exact-active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}

.app-main {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: transparent;
}
</style>
