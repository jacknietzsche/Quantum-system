<template>
  <div class="portfolio-summary">
    <el-card>
      <template #header>
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <el-icon><Wallet /></el-icon>
            <span class="font-semibold">组合概览</span>
          </div>
          <el-radio-group v-model="portfolioType" size="small">
            <el-radio-button label="value">价值</el-radio-button>
            <el-radio-button label="momentum">趋势</el-radio-button>
            <el-radio-button label="limit_up">涨停</el-radio-button>
          </el-radio-group>
        </div>
      </template>
      
      <div class="summary-grid">
        <div class="summary-item">
          <div class="summary-label">总资产</div>
          <div class="summary-value">¥{{ formatNumber(summary.total_assets) }}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">持仓市值</div>
          <div class="summary-value">¥{{ formatNumber(summary.market_value) }}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">现金</div>
          <div class="summary-value">¥{{ formatNumber(summary.cash) }}</div>
        </div>
        <div class="summary-item" :class="summary.total_pnl >= 0 ? 'profit' : 'loss'">
          <div class="summary-label">总盈亏</div>
          <div class="summary-value">
            {{ summary.total_pnl >= 0 ? '+' : '' }}¥{{ formatNumber(summary.total_pnl) }}
            <span class="pnl-pct">({{ summary.total_pnl_pct >= 0 ? '+' : '' }}{{ summary.total_pnl_pct }}%)</span>
          </div>
        </div>
      </div>
      
      <!-- 持仓分布 -->
      <div class="holdings-section" v-if="holdings.length > 0">
        <h4>持仓分布</h4>
        <div ref="chartRef" style="height: 200px"></div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, nextTick } from 'vue'
import { get } from '@/api/request'
import * as echarts from 'echarts'
import { Wallet } from '@element-plus/icons-vue'

const portfolioType = ref('value')
const summary = ref<any>({
  total_assets: 0,
  market_value: 0,
  cash: 0,
  total_pnl: 0,
  total_pnl_pct: 0,
})
const holdings = ref<any[]>([])
const chartRef = ref<HTMLElement>()
let chart: echarts.ECharts | null = null

const loadData = async () => {
  try {
    const [summaryRes, holdingsRes] = await Promise.all([
      get('/api/portfolio/summary'),
      get('/api/portfolio/holdings'),
    ])
    
    if (summaryRes) {
      summary.value = summaryRes
    }
    
    if (holdingsRes?.positions) {
      holdings.value = holdingsRes.positions
      await nextTick()
      renderChart()
    }
  } catch (e) {
    console.error('Failed to load portfolio:', e)
  }
}

const renderChart = () => {
  if (!chartRef.value || holdings.value.length === 0) return
  
  if (chart) {
    chart.dispose()
  }
  
  chart = echarts.init(chartRef.value)
  
  const data = holdings.value.slice(0, 10).map(h => ({
    name: h.stock_name || h.stock_code,
    value: h.market_value || h.quantity * h.buy_price,
  }))
  
  chart.setOption({
    tooltip: {
      trigger: 'item',
      formatter: '{b}: ¥{c} ({d}%)'
    },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      avoidLabelOverlap: false,
      itemStyle: {
        borderRadius: 10,
        borderColor: '#fff',
        borderWidth: 2
      },
      label: {
        show: false,
        position: 'center'
      },
      emphasis: {
        label: {
          show: true,
          fontSize: 14,
          fontWeight: 'bold'
        }
      },
      labelLine: {
        show: false
      },
      data,
    }]
  })
}

const formatNumber = (num: number) => {
  if (!num) return '0'
  if (Math.abs(num) >= 100000000) {
    return (num / 100000000).toFixed(2) + '亿'
  }
  if (Math.abs(num) >= 10000) {
    return (num / 10000).toFixed(2) + '万'
  }
  return num.toFixed(2)
}

watch(portfolioType, loadData)
onMounted(loadData)
</script>

<style scoped>
.portfolio-summary {
  margin-bottom: 20px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.summary-item {
  text-align: center;
  padding: 16px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
}

.summary-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}

.summary-value {
  font-size: 18px;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
}

.summary-item.profit .summary-value {
  color: #f56c6c;
}

.summary-item.loss .summary-value {
  color: #67c23a;
}

.pnl-pct {
  font-size: 12px;
  margin-left: 4px;
}

.holdings-section {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.holdings-section h4 {
  margin: 0 0 12px 0;
  font-size: 14px;
}
</style>