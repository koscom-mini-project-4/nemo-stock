import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { public: true },
    },
    {
      path: '/',
      name: 'dashboard',
      component: () => import('@/views/DashboardView.vue'),
    },
    {
      path: '/strategies/new',
      name: 'strategy-new',
      component: () => import('@/views/StrategyBuilderView.vue'),
    },
    {
      path: '/strategies/:id',
      name: 'strategy-edit',
      component: () => import('@/views/StrategyBuilderView.vue'),
      props: true,
    },
    {
      path: '/backtests/:id',
      name: 'backtest-result',
      component: () => import('@/views/BacktestResultView.vue'),
      props: true,
    },
    {
      path: '/ai/generate',
      name: 'ai-generate',
      component: () => import('@/views/AIGenerateView.vue'),
    },
    {
      path: '/admin',
      name: 'admin',
      component: () => import('@/views/AdminView.vue'),
    },
  ],
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (!to.meta.public && !auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.name === 'login' && auth.isAuthenticated) {
    return { name: 'dashboard' }
  }
  return true
})

export default router
