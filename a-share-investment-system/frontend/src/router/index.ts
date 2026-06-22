import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/dashboard' },
    {
      path: '/dashboard',
      name: 'Dashboard',
      component: () => import('@/views/Dashboard/index.vue'),
      meta: { title: '总览' },
    },
    {
      path: '/portfolio',
      redirect: '/portfolio/value',
    },
    {
      path: '/portfolio/:type',
      name: 'Portfolio',
      component: () => import('@/views/Portfolio/index.vue'),
      meta: { title: '持仓' },
    },
    {
      path: '/screening',
      name: 'Screening',
      component: () => import('@/views/Screening/index.vue'),
      meta: { title: '选股' },
    },
    {
      path: '/database',
      name: 'Database',
      component: () => import('@/views/Database/index.vue'),
      meta: { title: '数据库' },
    },
    {
      path: '/logs',
      name: 'Logs',
      component: () => import('@/views/Logs/index.vue'),
      meta: { title: '日志' },
    },
    // --- 新增页面 ---
    {
      path: '/analysis/single',
      name: 'SingleAnalysis',
      component: () => import('@/views/Analysis/SingleAnalysis.vue'),
      meta: { title: '单股分析' },
    },
    {
      path: '/analysis/batch',
      name: 'BatchAnalysis',
      component: () => import('@/views/Analysis/BatchAnalysis.vue'),
      meta: { title: '批量分析' },
    },
    {
      path: '/analysis/history',
      name: 'AnalysisHistory',
      component: () => import('@/views/Analysis/AnalysisHistory.vue'),
      meta: { title: '分析历史' },
    },
    {
      path: '/reports',
      name: 'Reports',
      component: () => import('@/views/Reports/index.vue'),
      meta: { title: '报告' },
    },
    {
      path: '/reports/:id',
      name: 'ReportDetail',
      component: () => import('@/views/Reports/ReportDetail.vue'),
      meta: { title: '报告详情' },
    },
    {
      path: '/tracking-board',
      name: 'TrackingBoard',
      component: () => import('@/views/TrackingBoard/index.vue'),
      meta: { title: '跟踪看板' },
    },
    {
      path: '/favorites',
      name: 'Favorites',
      component: () => import('@/views/Favorites/index.vue'),
      meta: { title: '自选' },
    },
    {
      path: '/tasks',
      name: 'TaskCenter',
      component: () => import('@/views/Tasks/TaskCenter.vue'),
      meta: { title: '任务中心' },
    },
    {
      path: '/screening/compare',
      name: 'ScreeningCompare',
      component: () => import('@/views/Screening/Compare.vue'),
      meta: { title: '风格对比' },
    },
    {
      path: '/database/quality',
      name: 'DataQuality',
      component: () => import('@/views/Database/DataQuality.vue'),
      meta: { title: 'Data Quality' },
    },
    {
      path: '/settings',
      name: 'Settings',
      component: () => import('@/views/Settings/index.vue'),
      meta: { title: '设置' },
    },
    {
      path: '/ai/decision',
      name: 'DecisionCenter',
      component: () => import('@/views/DecisionCenter/index.vue'),
      meta: { title: '决策中心' },
    },
    {
      path: '/ai/memory',
      name: 'AIMemory',
      component: () => import('@/views/AIMemory/index.vue'),
      meta: { title: 'AI复盘' },
    },
    {
      path: '/workflow',
      name: 'Workflow',
      component: () => import('@/views/Workflow/index.vue'),
      meta: { title: '工作流' },
    },
    {
      path: '/about',

      name: 'About',
      component: () => import('@/views/About/index.vue'),
      meta: { title: '关于' },
    },
  ],
})

router.beforeEach((to, from, next) => {
  if (to.meta.title) {
    document.title = `${to.meta.title} - AShare Investment System`
  }
  next()
})

export default router
