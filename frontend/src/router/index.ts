import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
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

export default router
