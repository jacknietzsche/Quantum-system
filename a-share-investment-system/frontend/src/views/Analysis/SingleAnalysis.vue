<template>
  <div class="single-analysis">
    <TaskProgressBanner v-if="isAnalyzing" :visible="true" title="股票分析中" :status="jobStatus" :progress="progress" :current-stage="currentStage" />

    <div class="flex gap-4 mb-4">
      <el-input v-model="stockCode" placeholder="输入股票代码，如 600519" style="width: 200px" size="large" />
      <el-button type="primary" size="large" @click="startAnalysis" :loading="isAnalyzing">
        <el-icon><VideoPlay /></el-icon> 开始分析
      </el-button>
      <el-button v-if="result" text @click="showDebate = true">
        <el-icon><ChatDotSquare /></el-icon> 辩论详情
      </el-button>
    </div>

    <el-row :gutter="16" v-if="result">
      <!-- 左侧：K线图 -->
      <el-col :span="24" class="mb-4">
        <el-card>
          <template #header><span class="font-semibold">{{ stockCode }} K线图</span></template>
          <KlineChart :data="klineData" :symbol="stockCode" />
        </el-card>
      </el-col>

      <!-- 决策 + 风险 -->
      <el-col :span="8" class="mb-4">
        <el-card class="mb-4">
          <DecisionCard :decision="result.signal" :confidence="result.confidence" :target-price="result.target_price" :stop-loss="result.stop_loss" :reasoning="result.reasoning" />
        </el-card>
        <el-card>
          <RiskItems :items="riskItems" />
        </el-card>
      </el-col>

      <!-- Agent协作图 -->
      <el-col :span="16" class="mb-4">
        <el-card>
          <template #header><span class="font-semibold">Agent协作图</span></template>
          <AgentGraph :agents="agentList" />
        </el-card>
      </el-col>

      <!-- 报告 -->
      <el-col :span="24">
        <el-card>
          <template #header><span class="font-semibold">分析报告</span></template>
          <ReportViewer :sections="reportSections" @export="exportReport" />
        </el-card>
      </el-col>
    </el-row>

    <el-empty v-if="!result && !isAnalyzing" description="输入股票代码并点击开始分析" class="mt-10" />

    <ChatCopilot v-if="result" class="chat-fab" />

    <DebatePanel v-if="showDebate" mode="research" :rounds="debateRounds" @close="showDebate = false" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { VideoPlay, ChatDotSquare } from '@element-plus/icons-vue'
import { analysisApi } from '@/api/analysis'
import { useAnalysisStore } from '@/stores/analysis'
import KlineChart from '@/components/KlineChart.vue'
import AgentGraph from '@/components/AgentGraph.vue'
import DecisionCard from '@/components/DecisionCard.vue'
import RiskItems from '@/components/RiskItems.vue'
import ReportViewer from '@/components/ReportViewer.vue'
import TaskProgressBanner from '@/components/TaskProgressBanner.vue'
import ChatCopilot from '@/components/ChatCopilot.vue'
import DebatePanel from '@/components/DebatePanel.vue'

const store = useAnalysisStore()
const stockCode = ref('')
const result = ref<any>(null)
const showDebate = ref(false)

const isAnalyzing = computed(() => store.isAnalyzing)
const jobStatus = computed(() => store.jobStatus)
const progress = computed(() => store.progress)
const currentStage = computed(() => {
  if (progress.value < 30) return '正在获取数据...'
  if (progress.value < 60) return '分析师团队工作中...'
  if (progress.value < 90) return '生成报告...'
  return '即将完成'
})

const agentList = computed(() => store.agents)
const klineData = ref<any[]>([])
const reportSections = computed(() => {
  if (!result.value) return []
  return [
    { title: '市场分析', content: JSON.stringify(result.value.market_analysis || {}, null, 2) },
    { title: '基本面分析', content: JSON.stringify(result.value.fundamental_analysis || {}, null, 2) },
    { title: '决策建议', content: JSON.stringify(result.value.trade_decision || {}, null, 2) },
    { title: '风险评估', content: JSON.stringify(result.value.risk_assessment || {}, null, 2) },
  ]
})
const riskItems = computed(() => {
  const r = result.value?.risk_assessment
  if (!r) return []
  return Object.entries(r).slice(0, 5).map(([k, v]) => ({
    title: k,
    description: String(v).slice(0, 100),
    severity: 'medium' as const,
  }))
})
const debateRounds = ref<any[]>([])

const startAnalysis = async () => {
  if (!stockCode.value.trim()) return
  result.value = null
  store.reset()

  try {
    store.setJob(stockCode.value)
    const res = await analysisApi.getAnalysis(stockCode.value.trim())
    result.value = res
    store.updateAgentStatus('analyst', 'completed')
    store.updateAgentStatus('researcher', 'completed')
    store.updateAgentStatus('trader', 'completed')
  } catch (e: any) {
    ElMessage.error(`分析失败: ${e.message}`)
  }
}

const exportReport = () => {
  if (!result.value) return
  const blob = new Blob([JSON.stringify(result.value, null, 2)], { type: 'text/markdown' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${stockCode.value}_分析报告.md`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('报告已导出')
}
</script>

<style lang="scss" scoped>
.chat-fab {
  position: fixed;
  bottom: 20px;
  right: 20px;
  width: 360px;
  max-height: 500px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.1);
  z-index: 100;
}
</style>
