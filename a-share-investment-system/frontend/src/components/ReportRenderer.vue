<template>
  <div class="report-renderer">
    <!-- Header -->
    <div class="report-header">
      <div class="stock-info">
        <h1 class="stock-title">
          <span class="stock-code">{{ data.stock_code }}</span>
          <span class="stock-name">{{ data.stock_name || '' }}</span>
        </h1>
        <div class="signal-bar">
          <el-tag :type="signalType" size="large" effect="dark">
            {{ signalText }}
          </el-tag>
          <div class="confidence">
            <span class="label">置信度</span>
            <el-progress :percentage="Number(data.confidence || 0)" :color="signalColor" :stroke-width="10" />
          </div>
        </div>
      </div>
      <div class="meta-info">
        <div class="meta-item">
          <span class="meta-label">分析日期</span>
          <span class="meta-value">{{ String(data.analysis_date || "") }}</span>
        </div>
      </div>
    </div>

    <!-- Trade Decision -->
    <div class="section" v-if="data.result?.trade_decision">
      <div class="section-header">
        <el-icon><TrendCharts /></el-icon>
        <span>交易决策</span>
      </div>
      <div class="section-body">
        <div class="decision-box" :class="signalClass">
          <div class="decision-action">{{ getActionText(data.result.trade_decision.action) }}</div>
          <div class="decision-reason" v-if="data.result.trade_decision.reasoning">
            {{ data.result.trade_decision.reasoning }}
          </div>
        </div>
      </div>
    </div>

    <!-- Key Metrics -->
    <div class="section" v-if="data.result?.fundamental_analysis">
      <div class="section-header">
        <el-icon><DataAnalysis /></el-icon>
        <span>核心指标</span>
      </div>
      <div class="section-body">
        <div class="metrics-grid">
          <div class="metric-card" v-for="(item, key) in fundamentalMetrics" :key="key">
            <div class="metric-value">{{ item.value }}</div>
            <div class="metric-label">{{ item.label }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Market Analysis -->
    <div class="section" v-if="data.result?.market_analysis">
      <div class="section-header">
        <el-icon><DataLine /></el-icon>
        <span>市场分析</span>
      </div>
      <div class="section-body">
        <div class="market-info">
          <div class="info-row">
            <span class="info-label">市场状态</span>
            <el-tag size="small">{{ data.result.market_analysis.regime || 'N/A' }}</el-tag>
          </div>
          <div class="info-row">
            <span class="info-label">趋势</span>
            <span>{{ data.result.market_analysis.trend || 'N/A' }}</span>
          </div>
          <div class="info-row" v-if="data.result.market_analysis.support">
            <span class="info-label">支撑位</span>
            <span class="price">{{ data.result.market_analysis.support }}</span>
          </div>
          <div class="info-row" v-if="data.result.market_analysis.resistance">
            <span class="info-label">阻力位</span>
            <span class="price">{{ data.result.market_analysis.resistance }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Valuation -->
    <div class="section" v-if="data.result?.valuation">
      <div class="section-header">
        <el-icon><Money /></el-icon>
        <span>估值分析</span>
      </div>
      <div class="section-body">
        <div class="valuation-grid">
          <div class="valuation-card" v-for="(val, key) in data.result.valuation" :key="String(key)">
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
    </div>

    <!-- Risk Assessment -->
    <div class="section" v-if="data.result?.risk_assessment">
      <div class="section-header">
        <el-icon><Warning /></el-icon>
        <span>风险评估</span>
      </div>
      <div class="section-body">
        <div class="risk-grid">
          <div class="risk-item" v-for="(val, key) in data.result.risk_assessment" :key="String(key)">
            <span class="risk-label">{{ getRiskLabel(String(key)) }}</span>
            <el-tag :type="getRiskType(val)" size="small">{{ val }}</el-tag>
          </div>
        </div>
      </div>
    </div>

    <!-- Target Price -->
    <div class="section" v-if="data.result?.target_price || data.result?.stop_loss">
      <div class="section-header">
        <el-icon><Aim /></el-icon>
        <span>目标价位</span>
      </div>
      <div class="section-body">
        <div class="price-targets">
          <div class="price-card target" v-if="data.result.target_price">
            <div class="price-label">目标价</div>
            <div class="price-value">¥{{ data.result.target_price }}</div>
          </div>
          <div class="price-card stop" v-if="data.result.stop_loss">
            <div class="price-label">止损价</div>
            <div class="price-value">¥{{ data.result.stop_loss }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Factors -->
    <div class="section" v-if="data.result?.factors && data.result.factors.length > 0">
      <div class="section-header">
        <el-icon><List /></el-icon>
        <span>关键因子</span>
      </div>
      <div class="section-body">
        <div class="factors-list">
          <div class="factor-item" v-for="(f, i) in data.result.factors" :key="i">
            <span class="factor-name">{{ f.name || f.factor_name }}</span>
            <span class="factor-score">{{ f.score }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { TrendCharts, DataAnalysis, DataLine, Money, Warning, Aim, List } from '@element-plus/icons-vue'

const props = defineProps<{
  data: any
}>()

const signalType = computed(() => {
  const s = props.data.signal
  if (s === 'bullish') return 'success'
  if (s === 'bearish') return 'danger'
  return 'warning'
})

const signalText = computed(() => {
  const s = props.data.signal
  if (s === 'bullish') return '看多'
  if (s === 'bearish') return '看空'
  return '中性'
})

const signalColor = computed(() => {
  const s = props.data.signal
  if (s === 'bullish') return '#67c23a'
  if (s === 'bearish') return '#f56c6c'
  return '#e6a23c'
})

const signalClass = computed(() => {
  const s = props.data.signal
  if (s === 'bullish') return 'signal-up'
  if (s === 'bearish') return 'signal-down'
  return 'signal-neutral'
})

const fundamentalMetrics = computed(() => {
  const fa = props.data.result?.fundamental_analysis
  if (!fa) return []
  const metrics = []
  if (fa.pe_ttm) metrics.push({ label: 'PE(TTM)', value: fa.pe_ttm })
  if (fa.roe) metrics.push({ label: 'ROE', value: fa.roe + '%' })
  if (fa.gross_margin) metrics.push({ label: '毛利率', value: fa.gross_margin + '%' })
  if (fa.eps) metrics.push({ label: 'EPS', value: '¥' + fa.eps })
  if (fa.debt_to_equity) metrics.push({ label: '资产负债率', value: fa.debt_to_equity + '%' })
  return metrics
})

const getActionText = (action: string) => {
  const map: Record<string, string> = {
    'bullish': '建议买入',
    'bearish': '建议卖出',
    'hold': '建议持有',
    'buy': '建议买入',
    'sell': '建议卖出',
  }
  return map[action] || action
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
    'max_drawdown_risk': '最大回撤风险',
    'liquidity_risk': '流动性风险',
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
.report-renderer {
  max-width: 900px;
  margin: 0 auto;
  padding: 20px;
}

.report-header {
  background: linear-gradient(135deg, var(--el-bg-color-page) 0%, var(--el-bg-color) 100%);
  border-radius: 12px;
  padding: 24px;
  margin-bottom: 20px;
  border: 1px solid var(--el-border-color-lighter);
}

.stock-title {
  font-size: 24px;
  margin: 0 0 16px 0;
  display: flex;
  align-items: center;
  gap: 12px;
}

.stock-code {
  color: var(--accent-blue, #409eff);
  font-family: 'JetBrains Mono', monospace;
}

.stock-name {
  color: var(--el-text-color-primary);
}

.signal-bar {
  display: flex;
  align-items: center;
  gap: 24px;
}

.confidence {
  flex: 1;
  max-width: 300px;
}

.confidence .label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
  display: block;
}

.meta-info {
  margin-top: 16px;
  display: flex;
  gap: 24px;
}

.meta-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.meta-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.meta-value {
  font-size: 14px;
  font-weight: 500;
}

.section {
  margin-bottom: 20px;
  background: var(--el-bg-color);
  border-radius: 12px;
  border: 1px solid var(--el-border-color-lighter);
  overflow: hidden;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px 20px;
  background: var(--el-fill-color-light);
  font-weight: 600;
  font-size: 15px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.section-body {
  padding: 20px;
}

.decision-box {
  padding: 20px;
  border-radius: 8px;
  text-align: center;
}

.decision-box.signal-up {
  background: linear-gradient(135deg, #f0f9ff 0%, #e1f5fe 100%);
  border: 1px solid #81d4fa;
}

.decision-box.signal-down {
  background: linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%);
  border: 1px solid #ffcc80;
}

.decision-box.signal-neutral {
  background: linear-gradient(135deg, #f5f5f5 0%, #eeeeee 100%);
  border: 1px solid #e0e0e0;
}

.decision-action {
  font-size: 20px;
  font-weight: 700;
  margin-bottom: 8px;
}

.decision-reason {
  font-size: 14px;
  color: var(--el-text-color-secondary);
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 16px;
}

.metric-card {
  text-align: center;
  padding: 16px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
}

.metric-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--el-text-color-primary);
  font-family: 'JetBrains Mono', monospace;
}

.metric-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}

.market-info {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid var(--el-border-color-extra-light);
}

.info-label {
  color: var(--el-text-color-secondary);
}

.price {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.valuation-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 16px;
}

.valuation-card {
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
  color: var(--el-text-color-primary);
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

.price-targets {
  display: flex;
  gap: 20px;
}

.price-card {
  flex: 1;
  padding: 20px;
  border-radius: 8px;
  text-align: center;
}

.price-card.target {
  background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%);
  border: 1px solid #a5d6a7;
}

.price-card.stop {
  background: linear-gradient(135deg, #fbe9e7 0%, #ffccbc 100%);
  border: 1px solid #ffab91;
}

.price-label {
  font-size: 14px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}

.price-value {
  font-size: 24px;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
}

.factors-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.factor-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
}

.factor-name {
  color: var(--el-text-color-primary);
}

.factor-score {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 600;
  color: var(--accent-blue, #409eff);
}
</style>