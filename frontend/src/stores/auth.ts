import { defineStore } from 'pinia'

const STORAGE_KEY = 'nemo_stock_token'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: sessionStorage.getItem(STORAGE_KEY) || '',
  }),
  getters: {
    isAuthenticated: (state) => !!state.token,
  },
  actions: {
    setToken(token: string) {
      this.token = token
      sessionStorage.setItem(STORAGE_KEY, token)
    },
    logout() {
      this.token = ''
      sessionStorage.removeItem(STORAGE_KEY)
    },
  },
})
