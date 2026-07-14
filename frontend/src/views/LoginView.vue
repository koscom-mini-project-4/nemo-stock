<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { login } from '@/api/services'

const username = ref('admin')
const password = ref('')
const errorMessage = ref('')
const loading = ref(false)

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

async function handleSubmit() {
  errorMessage.value = ''
  loading.value = true
  try {
    const token = await login(username.value, password.value)
    auth.setToken(token)
    const redirect = (route.query.redirect as string) || '/'
    router.push(redirect)
  } catch {
    errorMessage.value = '아이디 또는 비밀번호가 올바르지 않습니다.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <form class="card login-card" @submit.prevent="handleSubmit">
      <h1>네모네모매매</h1>
      <p class="text-muted">AI 가이드 기반 노코드 자동매매 전략 빌더 (PoC)</p>

      <label>
        아이디
        <input v-model="username" type="text" autocomplete="username" required />
      </label>
      <label>
        비밀번호
        <input v-model="password" type="password" autocomplete="current-password" required />
      </label>

      <p v-if="errorMessage" class="error">{{ errorMessage }}</p>

      <button class="btn btn-primary" type="submit" :disabled="loading">
        {{ loading ? '로그인 중...' : '로그인' }}
      </button>
    </form>
  </div>
</template>

<style scoped>
.login-page {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.login-card {
  width: 340px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.login-card h1 {
  font-size: 20px;
  margin: 0;
}

label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
  color: var(--text-muted);
}

.error {
  color: var(--danger);
  font-size: 13px;
  margin: 0;
}
</style>
