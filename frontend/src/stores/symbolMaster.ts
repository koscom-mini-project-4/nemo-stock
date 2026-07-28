import { defineStore } from 'pinia'
import { fetchSymbols } from '@/api/services'

/** 종목코드 -> 한글 종목명 매핑을 세션 동안 캐싱한다(최초 1회만 API 호출). */
export const useSymbolMasterStore = defineStore('symbolMaster', {
  state: () => ({
    byCode: {} as Record<string, string>,
    loaded: false,
    loading: false,
  }),
  actions: {
    async ensureLoaded() {
      if (this.loaded || this.loading) return
      this.loading = true
      try {
        const symbols = await fetchSymbols()
        this.byCode = Object.fromEntries(symbols.map((s) => [s.symbol, s.name]))
        this.loaded = true
      } catch {
        // 매핑 없이도 화면은 종목코드만으로 정상 동작해야 하므로 조용히 무시한다.
      } finally {
        this.loading = false
      }
    },
  },
  getters: {
    /** 매핑에 없으면 코드 그대로("005930"), 있으면 "삼성전자(005930)" 형태로 반환. */
    displayName: (state) => (symbol: string) => {
      const name = state.byCode[symbol]
      return name ? `${name}(${symbol})` : symbol
    },
    /** 종목코드/한글 종목명 부분일치 검색(대소문자 무시, 자동완성용). ensureLoaded 후 사용. */
    search: (state) => (query: string, limit = 8) => {
      const q = query.trim()
      if (!q) return []
      const qLower = q.toLowerCase()
      const out: { symbol: string; name: string }[] = []
      for (const [symbol, name] of Object.entries(state.byCode)) {
        if (symbol.includes(q) || name.toLowerCase().includes(qLower)) {
          out.push({ symbol, name })
          if (out.length >= limit) break
        }
      }
      return out
    },
  },
})
