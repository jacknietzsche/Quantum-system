<template>
  <div class="stock-analysis-card">
    <el-card>
      <template #header>
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <el-icon><TrendCharts /></el-icon>
            <span class="font-semibold">股票分析</span>
          </div>
          <el-input
            v-model="stockCode"
            placeholder="输入股票代码"
            style="width: 200px"
            @keyup.enter="analyzeStock"
          >
            <template #append>
              <el-button @click="analyzeStock" :loading="loading">
                <el-icon><Search /></el-icon>
              </el-button>
            </template>
          </el-input>
        </div>
      </template>
      
      <div v-if="analysis" class="analysis-content">
        <!-- 股票信息 -->
        <div class="stock-header">
          <div class="stock-info">
            <h2>{{ analysis.stock_code }} {{ analysis.stock_name }}</h2>
            <el-tag :type="signalType" size="large">{{ signalText }}</el-tag>
          </div>
          <div class="stock-price">
            <span class="price" :class="priceClass">{{ analysis.current_price || '--' }}</span>
            <span class="change" :class="priceClass">
              {{ analysis.change_pct > 0 ? '+' : '' }}{{ analysis.change_pct || 0 }}%
            </span>
          </div>
        </div>
        
        <!-- 核心指标 -->
        <div class="metrics-grid">
          <div class="metric-item">
            <div class="metric-label">PE (TTM)</div>
            <div class="metric-value">{{ analysis.pe_ratio || '--' }}</div>
          </div>
          <div class="metric-item">
            <div class="metric-label">ROE</div>
            <div class="metric-value">{{ analysis.roe || '--' }}%</div>
          </div>
          <div class="metric-item">
            <div class="metric-label">毛利率</div>
            <div class="metric-value">{{ analysis.gross_margin || '--' }}%</div>
          </div>
          <div class="metric-item">
            <div class="metric-label">市值</div>
            <div class="metric-value">{{ formatMarketCap(analysis.market_cap) }}</div>
          </div>
        </div>
        
        <!-- 估值分析 -->
        <div class="valuation-section" v-if="analysis.valuation">
          <h3>估值分析</h3>
          <div class="valuation-grid">
            <div v-for="(val, key) in analysis.valuation" :key="key" class="valuation-item">
              <div class="valuation-header">
                <span class="valuation-name">{{ getAnalystName(String(key)) }}</span>
                <el-tag :type="getSignalType(val.signal)" size="small">{{ val.signal }}</el-tag>
              </div>
              <div class="valuation-score">
                <span class="score-value">{{ val.score }}</span>
                <span class="score-label">分</span>
              </div>
            </div>
          </div>
        </div>
        
        <!-- 风险评估 -->
        <div class="risk-section" v-if="analysis.risk_assessment">
          <h3>风险评估</h3>
          <div class="risk-grid">
            <div v-for="(val, key) in analysis.risk_assessment" :key="key" class="risk-item">
              <span class="risk-label">{{ getRiskLabel(String(key)) }}</span>
              <el-tag :type="getRiskType(val)" size="small">{{ val }}</el-tag>
            </div>
          </div>
        </div>
      </div>
      
      <div v-else-if="!loading" class="empty-state">
        <el-icon :size="48"><DataAnalysis /></el-icon>
        <p>输入股票代码开始分析</p>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { get } from '@/api/request'
import { ElMessage } from 'element-plus'
import { TrendCharts, Search, DataAnalysis } from '@element-plus/icons-vue'

const stockCode = ref('')
const loading = ref(false)
const analysis = ref<any>(null)

const signalType = computed(() => {
  if (!analysis.value) return 'info'
  const s = analysis.value.signal
  if (s === 'bullish') return 'success'
  if (s === 'bearish') return 'danger'
  return 'warning'
})

const signalText = computed(() => {
  if (!analysis.value) return ''
  const s = analysis.value.signal
  if (s === 'bullish') return '看多'
  if (s === 'bearish') return '看空'
  return '中性'
})

const priceClass = computed(() => {
  if (!analysis.value) return ''
  return analysis.value.change_pct >= 0 ? 'price-up' : 'price-down'
})

const analyzeStock = async () => {
  if (!stockCode.value.trim()) {
    ElMessage.warning('请输入股票代码')
    return
  }
  
  loading.value = true
  try {
    const res = await get(`/api/analysis/${stockCode.value.trim()}`) as any
    if (res.error) {
      ElMessage.error(res.error)
    } else {
      analysis.value = res
    }
  } catch (e) {
    ElMessage.error('分析失败')
  } finally {
    loading.value = false
  }
}

const formatMarketCap = (cap: number) => {
  if (!cap) return '--'
  if (cap >= 100000000) return (cap / 100000000).toFixed(1) + '亿'
  if (cap >= 10000) return (cap / 10000).toFixed(1) + '万'
  return cap.toString()
}

const getAnalystName = (key: string) => {
  const map: Record<string, string> = {
    'buffett': '巴菲特',
    'graham': '格雷厄姆',
    'lynch': '林奇',
    'taleb': '塔勒布',
    'munger': '芒格',
  }
  return map[key] || key
}

const getSignalType = (signal: string) => {
  if (signal === 'bullish') return 'success'
  if (signal === 'bearish') return 'danger'
  return 'warning'
}

const getRiskLabel = (key: string) => {
  const map: Record<string, string> = {
    'max_drawdown_risk': '最大回撤',
    'liquidity_risk': '流动性',
    'valuation_risk': '估值风险',
    'sector_risk': '行业风险',
  }
  return map[key] || key
}

const getRiskType = (risk: string) => {
  if (risk === 'low') return 'success'
  if (risk === 'high') return 'danger'
  return 'warning'
}
</script>

<style scoped>
.stock-analysis-card {
  margin-bottom: 20px;
}

.analysis-content {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.stock-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.stock-info h2 {
  margin: 0 0 8px 0;
  font-size: 20px;
}

.stock-price {
  text-align: right;
}

.price {
  font-size: 28px;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
}

.change {
  display: block;
  font-size: 16px;
  font-weight: 600;
}

.price-up {
  color: #f56c6c;
}

.price-down {
  color: #67c23a;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.metric-item {
  text-align: center;
  padding: 16px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
}

.metric-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}

.metric-value {
  font-size: 20px;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
}

.valuation-section,
.risk-section {
  padding-top: 16px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.valuation-section h3,
.risk-section h3 {
  margin: 0 0 16px 0;
  font-size: 16px;
}

.valuation-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 16px;
}

.valuation-item {
  padding: 16px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
  text-align: center;
}

.valuation-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.valuation-name {
  font-weight: 600;
}

.valuation-score {
  display: flex;
  align-items: baseline;
  justify-content: center;
  gap: 4px;
}

.score-value {
  font-size: 32px;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
}

.score-label {
  font-size: 14px;
  color: var(--el-text-color-secondary);
}

.risk-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}

.risk-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
}

.risk-label {
  color: var(--el-text-color-secondary);
}

.empty-state {
  text-align: center;
  padding: 40px 0;
  color: var(--el-text-color-secondary);
}

.empty-state p {
  margin-top: 12px;
}
</style>