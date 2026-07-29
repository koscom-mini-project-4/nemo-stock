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
    /** 종목코드/한글 종목명 검색(대소문자 무시, 자동완성용). ensureLoaded 후 사용.
     * "삼성" 같은 짧은 검색어에도 원하는 종목(예: 삼성전자)이 상위에 오도록 일치도로 정렬한다
     * — 이름/코드가 검색어로 "시작"하는 항목을 부분일치보다 우선한다. */
    search: (state) => (query: string, limit = 8) => {
      const q = query.trim()
      if (!q) return []
      const qLower = q.toLowerCase()
      const ranked: { symbol: string; name: string; rank: number }[] = []
      for (const [symbol, name] of Object.entries(state.byCode)) {
        const nameLower = name.toLowerCase()
        let rank = -1
        if (symbol === q || nameLower === qLower) rank = 0
        else if (symbol.startsWith(q) || nameLower.startsWith(qLower)) rank = 1
        else if (symbol.includes(q) || nameLower.includes(qLower)) rank = 2
        if (rank >= 0) ranked.push({ symbol, name, rank })
      }
      ranked.sort((a, b) => a.rank - b.rank || a.name.length - b.name.length)
      return ranked.slice(0, limit).map(({ symbol, name }) => ({ symbol, name }))
    },
  },
})
