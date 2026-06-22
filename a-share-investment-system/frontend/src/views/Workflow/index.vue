<template>
  <div class="workflow-page">
    <div class="page-header mb-4">
      <h2 class="text-xl font-bold">日频工作流</h2>
      <span class="mono text-xs" style="color: var(--text-muted)">Multi-Agent Daily Pipeline</span>
    </div>

    <!-- V2 Multi-Agent Analysis -->
    <el-card class="mb-4">
      <template #header>
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <el-icon><Cpu /></el-icon>
            <span class="font-semibold">V2 多Agent深度分析</span>
          </div>
          <div class="flex gap-2">
            <el-input v-model="stockCode" placeholder="股票代码 如 600519" style="width: 160px" size="small" />
            <el-button type="primary" size="small" @click="runV2Analysis" :loading="analyzing">
              <el-icon><VideoPlay /></el-icon> 分析
            </el-button>
          </div>
        </div>
      </template>

      <div v-if="!v2Result && !analyzing" class="text-center py-8" style="color: var(--text-muted)">
        输入股票代码，运行多Agent深度分析
      </div>

      <div v-if="analyzing" class="text-center py-8">
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        <div class="mt-2 mono text-sm">多Agent分析中，请稍候...</div>
      </div>

      <div v-if="v2Result">
        <!-- Decision -->
        <div class="decision-banner mb-4 p-4 rounded-lg" :class="decisionClass">
          <div class="flex items-center justify-between mb-2">
            <span class="text-lg font-bold">{{ v2Result.stock_code }} 决策</span>
            <el-tag :type="actionTagType" size="large" effect="dark">
              {{ v2Result.signal?.action?.toUpperCase() || 'HOLD' }}
            </el-tag>
          </div>
          <div class="mb-2">
            <span class="mono text-sm">置信度: </span>
            <el-progress :percentage="Math.round((v2Result.signal?.confidence || 0) * 100)"
              :color="confidenceColor" style="display: inline-block; width: 200px" />
          </div>
          <div class="text-sm" style="white-space: pre-wrap">{{ v2Result.signal?.reasoning }}</div>
        </div>

        <!-- Analyst Reports -->
        <el-collapse v-if="Object.keys(v2Result.reports || {}).length">
          <el-collapse-item v-for="(content, key) in v2Result.reports" :key="key" :title="reportTitle(key)">
            <div class="mono text-xs" style="white-space: pre-wrap; max-height: 400px; overflow-y: auto">{{ content }}</div>
          </el-collapse-item>
        </el-collapse>

        <!-- Debate -->
        <div v-if="v2Result.debate?.judge_decision" class="mt-4">
          <el-divider content-position="left">研究辩论</el-divider>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-card shadow="never" class="bull-card">
                <template #header><span class="font-semibold text-green-600">多头观点</span></template>
                <div class="mono text-xs" style="white-space: pre-wrap; max-height: 200px; overflow-y: auto">{{ v2Result.debate.bull_history }}</div>
              </el-card>
            </el-col>
            <el-col :span="12">
              <el-card shadow="never" class="bear-card">
                <template #header><span class="font-semibold text-red-600">空头观点</span></template>
                <div class="mono text-xs" style="white-space: pre-wrap; max-height: 200px; overflow-y: auto">{{ v2Result.debate.bear_history }}</div>
              </el-card>
            </el-col>
          </el-row>
          <div class="mt-2 p-3 rounded" style="background: var(--el-fill-color-light)">
            <span class="font-semibold text-sm">裁判结论: </span>
            <span class="text-sm">{{ v2Result.debate.judge_decision }}</span>
          </div>
        </div>

        <!-- Risk Debate -->
        <div v-if="v2Result.risk_debate?.aggressive" class="mt-4">
          <el-divider content-position="left">风控三方辩论</el-divider>
          <el-row :gutter="16">
            <el-col :span="8">
              <el-card shadow="never">
                <template #header><span class="font-semibold text-orange-500">激进派</span></template>
                <div class="mono text-xs" style="white-space: pre-wrap; max-height: 150px; overflow-y: auto">{{ v2Result.risk_debate.aggressive }}</div>
              </el-card>
            </el-col>
            <el-col :span="8">
              <el-card shadow="never">
                <template #header><span class="font-semibold text-blue-500">保守派</span></template>
                <div class="mono text-xs" style="white-space: pre-wrap; max-height: 150px; overflow-y: auto">{{ v2Result.risk_debate.conservative }}</div>
              </el-card>
            </el-col>
            <el-col :span="8">
              <el-card shadow="never">
                <template #header><span class="font-semibold text-gray-500">中立派</span></template>
                <div class="mono text-xs" style="white-space: pre-wrap; max-height: 150px; overflow-y: auto">{{ v2Result.risk_debate.neutral }}</div>
              </el-card>
            </el-col>
          </el-row>
        </div>

        <!-- Final Decision -->
        <div v-if="v2Result.final_decision" class="mt-4">
          <el-divider content-position="left">最终决策</el-divider>
          <div class="p-3 rounded" style="background: var(--el-fill-color-light); white-space: pre-wrap">
            <div class="mono text-sm">{{ v2Result.final_decision }}</div>
          </div>
        </div>
      </div>
    </el-card>

    <!-- Workflow Memory -->
    <el-row :gutter="16">
      <el-col :span="12">
        <el-card class="mb-4">
          <template #header>
            <div class="flex items-center justify-between">
              <span class="font-semibold">交易记忆</span>
              <el-tag size="small">{{ trades.length }} 条</el-tag>
            </div>
          </template>
          <div v-if="!trades.length" class="text-center py-4" style="color: var(--text-muted)">暂无交易记录</div>
          <div v-for="(t, i) in trades" :key="i" class="trade-item mb-2 p-2 rounded" style="background: var(--el-fill-color-lighter)">
            <div class="flex justify-between">
              <span class="font-semibold text-sm">{{ t.stock_code }} {{ t.stock_name }}</span>
              <el-tag :type="t.action === 'buy' ? 'success' : (t.action === 'sell' ? 'danger' : 'info')" size="small">
                {{ t.action }}
              </el-tag>
            </div>
            <div class="mono text-xs mt-1" style="color: var(--text-muted)">
              {{ t.price }} x {{ t.quantity }} | {{ t.timestamp?.slice(0, 16) }}
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card class="mb-4">
          <template #header>
            <div class="flex items-center justify-between">
              <span class="font-semibold">反思记录</span>
              <el-tag size="small">{{ reflections.length }} 条</el-tag>
            </div>
          </template>
          <div v-if="!reflections.length" class="text-center py-4" style="color: var(--text-muted)">暂无反思记录</div>
          <div v-for="(r, i) in reflections" :key="i" class="reflection-item mb-2 p-2 rounded" style="background: var(--el-fill-color-lighter)">
            <div class="flex justify-between mb-1">
              <span class="text-sm font-semibold">{{ r.stock_code }}</span>
              <div>
                <el-tag size="small" class="mr-1">{{ r.rating }}</el-tag>
                <span class="mono text-xs" :class="r.raw_return >= 0 ? 'text-green-500' : 'text-red-500'">
                  {{ r.raw_return >= 0 ? '+' : '' }}{{ (r.raw_return * 100).toFixed(1) }}%
                </span>
              </div>
            </div>
            <div class="text-xs" style="color: var(--text-secondary); white-space: pre-wrap">{{ r.reflection?.slice(0, 200) }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Performance -->
    <el-card v-if="performance" class="mb-4">
      <template #header><span class="font-semibold">交易表现</span></template>
      <el-descriptions :column="4" border size="small">
        <el-descriptions-item label="总交易数">{{ performance.total_trades || 0 }}</el-descriptions-item>
        <el-descriptions-item label="胜率">{{ ((performance.win_rate || 0) * 100).toFixed(1) }}%</el-descriptions-item>
        <el-descriptions-item label="平均收益">{{ ((performance.avg_return || 0) * 100).toFixed(2) }}%</el-descriptions-item>
        <el-descriptions-item label="最大回撤">{{ ((performance.max_drawdown || 0) * 100).toFixed(2) }}%</el-descriptions-item>
      </el-descriptions>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { VideoPlay, Cpu, Loading } from '@element-plus/icons-vue'
import { v2Api, type V2AnalysisResult } from '@/api/v2'

const stockCode = ref('')
const analyzing = ref(false)
const v2Result = ref<V2AnalysisResult | null>(null)
const trades = ref<any[]>([])
const reflections = ref<any[]>([])
const performance = ref<any>(null)

const decisionClass = computed(() => {
  const action = v2Result.value?.signal?.action || ''
  if (action.includes('buy')) return 'decision-buy'
  if (action.includes('sell')) return 'decision-sell'
  return 'decision-hold'
})

const actionTagType = computed(() => {
  const action = v2Result.value?.signal?.action || ''
  if (action.includes('buy')) return 'success'
  if (action.includes('sell')) return 'danger'
  return 'warning'
})

const confidenceColor = computed(() => {
  const c = (v2Result.value?.signal?.confidence || 0) * 100
  if (c >= 70) return '#67c23a'
  if (c >= 40) return '#e6a23c'
  return '#f56c6c'
})

const reportTitle = (key: string) => {
  const map: Record<string, string> = {
    market_report: '技术分析',
    sentiment_report: '情绪分析',
    news_report: '新闻分析',
    fundamentals_report: '基本面分析',
    northbound_report: '北向资金',
    sector_report: '板块分析',
  }
  return map[key] || key
}

const runV2Analysis = async () => {
  if (!stockCode.value.trim()) return
  analyzing.value = true
  v2Result.value = null
  try {
    const res = await v2Api.analyzeStock(stockCode.value.trim())
    if (res.ok) {
      v2Result.value = res
      ElMessage.success('分析完成')
    } else {
      ElMessage.error(res.error || '分析失败')
    }
  } catch (e: any) {
    ElMessage.error(`分析失败: ${e.message}`)
  } finally {
    analyzing.value = false
  }
}

onMounted(async () => {
  try {
    const [tradesRes, refRes, perfRes] = await Promise.all([
      v2Api.getTrades(20).catch(() => ({ trades: [] })),
      v2Api.getReflections(10).catch(() => ({ reflections: [] })),
      v2Api.getPerformance().catch(() => ({ performance: {} })),
    ])
    trades.value = tradesRes.trades || []
    reflections.value = refRes.reflections || []
    performance.value = perfRes.performance || null
  } catch {
    // Silent fail on mount
  }
})
</script>

<style scoped>
.decision-buy { background: rgba(103, 194, 58, 0.1); border-left: 4px solid #67c23a; }
.decision-sell { background: rgba(245, 108, 108, 0.1); border-left: 4px solid #f56c6c; }
.decision-hold { background: rgba(230, 162, 60, 0.1); border-left: 4px solid #e6a23c; }
.bull-card { border-top: 2px solid #67c23a; }
.bear-card { border-top: 2px solid #f56c6c; }
.trade-item:hover, .reflection-item:hover { background: var(--el-fill-color-light); }
</style>
