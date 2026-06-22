<template>
  <div class="portfolio-container">
    <div class="space-y-4 max-w-6xl">
      <!-- 标题栏 -->
      <div class="page-header">
        <div class="header-left">
          <h1 class="text-lg font-semibold tracking-wide mono" style="color: var(--text-primary)">
            {{ PORTFOLIO_CONFIGS[activePortfolio].icon }} PORTFOLIO
          </h1>
          <div class="header-meta" v-if="currentSummary">
            <span class="stat-dot" :style="{ background: PORTFOLIO_CONFIGS[activePortfolio].color }" />
            <span class="meta-text">{{ PORTFOLIO_CONFIGS[activePortfolio].label }}</span>
            <span class="meta-divider" />
            <span class="meta-text">{{ PORTFOLIO_CONFIGS[activePortfolio].desc }}</span>
          </div>
        </div>
        <div class="header-right flex items-center gap-2">
          <el-button size="small" :loading="loading" @click="refreshAll">
            <el-icon><Refresh /></el-icon>
            Refresh
          </el-button>
          <el-button type="danger" size="small" plain @click="handleReset">
            <template #icon><el-icon><Delete /></el-icon></template>
            Reset
          </el-button>
          <el-button type="primary" size="small" @click="showAddDialog = true">
            <template #icon><el-icon><Plus /></el-icon></template>
            Add Position
          </el-button>
        </div>
      </div>

      <!-- Portfolio Tabs -->
      <el-tabs :model-value="activePortfolio" @tab-change="onTabChange" class="style-tabs">
        <el-tab-pane
          v-for="pt in PORTFOLIO_TYPES" :key="pt"
          :label="`${PORTFOLIO_CONFIGS[pt].icon} ${PORTFOLIO_CONFIGS[pt].label}`"
          :name="pt"
        />
      </el-tabs>

      <!-- Summary Cards -->
      <div v-if="currentSummary" class="grid grid-cols-4 gap-3">
        <div class="card p-3 text-center">
          <div class="text-2xl font-bold mono" style="color: var(--accent-blue)">
            {{ currentSummary.total_asset.toLocaleString(undefined, { maximumFractionDigits: 2 }) }}
          </div>
          <div class="mono text-xs mt-1" style="color: var(--text-muted)">AUM</div>
        </div>
        <div class="card p-3 text-center">
          <div class="text-2xl font-bold mono" style="color: var(--text-secondary)">
            {{ currentSummary.cash.toLocaleString(undefined, { maximumFractionDigits: 2 }) }}
          </div>
          <div class="mono text-xs mt-1" style="color: var(--text-muted)">CASH</div>
        </div>
        <div class="card p-3 text-center">
          <div class="text-2xl font-bold mono" style="color: var(--text-secondary)">
            {{ currentSummary.position_count }}
          </div>
          <div class="mono text-xs mt-1" style="color: var(--text-muted)">POSITIONS</div>
        </div>
        <div class="card p-3 text-center">
          <div
            class="text-2xl font-bold mono"
            :class="(currentSummary.total_return_pct || 0) >= 0 ? 'num-up' : 'num-down'"
          >
            {{ (currentSummary.total_return_pct || 0).toFixed(2) }}%
          </div>
          <div class="mono text-xs mt-1" style="color: var(--text-muted)">TOTAL RETURN</div>
        </div>
      </div>

      <!-- NAV Chart -->
      <div class="card p-3">
        <div class="flex justify-between items-center mb-2">
          <span class="text-sm font-medium" style="color: var(--text-primary)">NAV</span>
        </div>
        <div ref="navChartRef" style="width: 100%; height: 240px"></div>
      </div>

      <!-- Holdings Table -->
      <div class="card overflow-hidden">
        <el-table
          v-loading="loading"
          :data="positions"
          style="width: 100%"
          @row-click="handleRowClick"
          empty-text=""
        >
          <el-table-column prop="stock_code" label="Code" width="100">
            <template #default="{ row }">
              <span class="mono text-sm" style="color: var(--accent-blue)">{{ row.stock_code }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="stock_name" label="Name" width="120" />
          <el-table-column label="Cost" width="90">
            <template #default="{ row }">
              <span class="mono" style="color: var(--text-secondary)">{{ (row.buy_price || 0).toFixed(2) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="Price" width="90">
            <template #default="{ row }">
              <span class="mono">{{ (row.current_price || 0).toFixed(2) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="Qty" width="80">
            <template #default="{ row }">
              <span class="mono text-xs" style="color: var(--text-secondary)">{{ row.quantity }}</span>
            </template>
          </el-table-column>
          <el-table-column label="Value" width="100">
            <template #default="{ row }">
              <span class="mono" style="color: var(--text-secondary)">
                {{ ((row.current_value || 0) / 10000).toFixed(2) }}<span class="text-xs">w</span>
              </span>
            </template>
          </el-table-column>
          <el-table-column label="P&L%" width="120">
            <template #default="{ row }">
              <span
                class="mono font-semibold flex items-center gap-1"
                :class="(row.profit_loss_pct || 0) >= 0 ? 'num-up' : 'num-down'"
              >
                <el-icon :size="14">
                  <Top v-if="(row.profit_loss_pct || 0) >= 0" />
                  <Bottom v-else />
                </el-icon>
                {{ (row.profit_loss_pct || 0).toFixed(1) }}%
              </span>
            </template>
          </el-table-column>
          <el-table-column label="Weight" width="80">
            <template #default="{ row }">
              <span class="mono text-xs" style="color: var(--text-secondary)">
                {{ getWeight(row).toFixed(1) }}%
              </span>
            </template>
          </el-table-column>
          <el-table-column label="Risk" width="70">
            <template #default="{ row }">
              <span class="mono text-xs" :class="getRiskClass(row)">
                {{ getRiskScore(row) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="Action" width="100" fixed="right">
            <template #default="{ row }">
              <el-button
                type="danger"
                size="small"
                text
                @click.stop="openSellDialog(row)"
              >
                SELL
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- Empty State -->
        <div v-if="!loading && positions.length === 0" class="text-center py-16 mono text-sm" style="color: var(--text-muted)">
          <div class="text-3xl mb-3">{{ PORTFOLIO_CONFIGS[activePortfolio].icon }}</div>
          <div>No positions in {{ PORTFOLIO_CONFIGS[activePortfolio].label }}</div>
          <div class="text-xs mt-2" style="color: var(--text-muted)">
            Add your first position or run screening to discover stocks
          </div>
        </div>
      </div>

      <!-- Add Position Dialog -->
      <el-dialog
        v-model="showAddDialog"
        title="Add Position"
        width="480px"
        :close-on-click-modal="false"
      >
        <el-form
          ref="addFormRef"
          :model="addForm"
          :rules="addRules"
          label-width="100px"
          label-position="left"
          size="small"
        >
          <el-form-item label="Stock Code" prop="stock_code">
            <el-input
              v-model="addForm.stock_code"
              placeholder="e.g. 600519"
              class="mono"
            />
          </el-form-item>
          <el-form-item label="Stock Name" prop="stock_name">
            <el-input
              v-model="addForm.stock_name"
              placeholder="Stock name"
            />
          </el-form-item>
          <el-form-item label="Buy Price" prop="buy_price">
            <el-input-number
              v-model="addForm.buy_price"
              :precision="2"
              :step="0.1"
              :min="0"
              style="width: 100%"
            />
          </el-form-item>
          <el-form-item label="Quantity" prop="quantity">
            <el-input-number
              v-model="addForm.quantity"
              :min="100"
              :step="100"
              style="width: 100%"
            />
          </el-form-item>
          <el-form-item label="Reason">
            <el-input
              v-model="addForm.buy_reason"
              type="textarea"
              :rows="2"
              placeholder="Why buy?"
            />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button size="small" @click="showAddDialog = false">Cancel</el-button>
          <el-button type="primary" size="small" :loading="submitting" @click="submitAdd">
            Confirm Buy
          </el-button>
        </template>
      </el-dialog>

      <!-- Sell Confirmation Dialog -->
      <el-dialog
        v-model="showSellDialog"
        title="Sell Position"
        width="400px"
        :close-on-click-modal="false"
      >
        <div v-if="sellTarget" class="space-y-3">
          <div class="flex items-center gap-2">
            <span class="font-medium">{{ sellTarget.stock_name }}</span>
            <span class="mono text-xs" style="color: var(--text-secondary)">{{ sellTarget.stock_code }}</span>
          </div>
          <div class="text-xs" style="color: var(--text-muted)">
            Current Price: <span class="mono">{{ (sellTarget.current_price || 0).toFixed(2) }}</span>
            &middot; Qty: <span class="mono">{{ sellTarget.quantity }}</span>
          </div>
          <el-form label-position="top" size="small">
            <el-form-item label="Sell Price">
              <el-input-number
                v-model="sellForm.sell_price"
                :precision="2"
                :step="0.1"
                :min="0"
                style="width: 100%"
              />
            </el-form-item>
            <el-form-item label="Sell Reason">
              <el-input
                v-model="sellForm.sell_reason"
                type="textarea"
                :rows="2"
                placeholder="Why sell?"
              />
            </el-form-item>
          </el-form>
        </div>
        <template #footer>
          <el-button size="small" @click="showSellDialog = false">Cancel</el-button>
          <el-button type="danger" size="small" :loading="submitting" @click="submitSell">
            Confirm Sell
          </el-button>
        </template>
      </el-dialog>

      <!-- Stock Detail Dialog -->
      <StockDetail
        v-if="selectedStock"
        :stock-code="selectedStock"
        @close="selectedStock = null"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { usePortfolioStore } from '@/stores/portfolio'
import { get, post, put } from '@/api/request'
import { PORTFOLIO_CONFIGS, PORTFOLIO_TYPES } from '@/types/portfolio'
import type { PortfolioType, PortfolioHoldings, Position } from '@/types/portfolio'
import { Top, Bottom, Plus, Delete, Refresh } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import StockDetail from '@/components/StockDetail.vue'
import * as echarts from 'echarts'

const route = useRoute()
const router = useRouter()
const store = usePortfolioStore()

const navChartRef = ref<HTMLDivElement | null>(null)
let chartInstance: echarts.ECharts | null = null
let refreshTimer: ReturnType<typeof setInterval> | null = null

// Active portfolio from route param
const activePortfolio = computed<PortfolioType>(() => {
  const t = route.params.type as string
  if (PORTFOLIO_TYPES.includes(t as PortfolioType)) return t as PortfolioType
  return 'value'
})

// Data
const holdings = computed(() => store.holdings)
const loading = computed(() => store.loading)
const nav = computed(() => store.nav)

const positions = computed(() => holdings.value?.positions || [])
const currentSummary = computed(() => store.summaries?.[activePortfolio.value] || null)

// Add Position Dialog
const showAddDialog = ref(false)
const submitting = ref(false)
const addFormRef = ref<any>(null)
const addForm = ref({
  stock_code: '',
  stock_name: '',
  buy_price: 0,
  quantity: 100,
  buy_reason: '',
})
const addRules = {
  stock_code: [{ required: true, message: 'Stock code required', trigger: 'blur' }],
  stock_name: [{ required: true, message: 'Stock name required', trigger: 'blur' }],
  buy_price: [{ required: true, type: 'number', min: 0.01, message: 'Valid price required', trigger: 'blur' }],
  quantity: [{ required: true, type: 'number', min: 100, message: 'Min 100 shares', trigger: 'blur' }],
}

// Sell Dialog
const showSellDialog = ref(false)
const sellTarget = ref<Position | null>(null)
const sellForm = ref({ sell_price: 0, sell_reason: '' })

const selectedStock = ref<string | null>(null)

// Computed helpers
const getWeight = (row: any) => {
  const totalAsset = holdings.value?.total_asset || 1
  return ((row.current_value || 0) / totalAsset) * 100
}

const getRiskScore = (row: any) => {
  const weight = getWeight(row)
  return Math.min(99, Math.round(Math.abs(row.profit_loss_pct || 0) * 3 + (weight > 20 ? 30 : 0) + 20))
}

const getRiskClass = (row: any) => {
  const score = getRiskScore(row)
  if (score < 30) return 'badge badge-up'
  if (score < 60) return 'badge badge-warn'
  return 'badge badge-down'
}

const handleRowClick = (row: any) => {
  selectedStock.value = row.stock_code
}

const openSellDialog = (row: any) => {
  sellTarget.value = row
  sellForm.value = { sell_price: row.current_price || 0, sell_reason: '' }
  showSellDialog.value = true
}

// Actions
async function refreshAll() {
  await Promise.all([
    store.fetchHoldings(activePortfolio.value),
    store.fetchAllSummaries(),
    store.fetchNav(activePortfolio.value),
  ])
}

async function onTabChange(tab: any) {
  if (typeof tab === 'string') {
    router.push(`/portfolio/${tab}`)
  }
}

async function submitAdd() {
  if (!addFormRef.value) return
  try {
    await addFormRef.value.validate()
  } catch {
    return
  }
  submitting.value = true
  try {
    await post('/api/portfolio/holdings', {
      portfolio_type: activePortfolio.value,
      stock_code: addForm.value.stock_code,
      stock_name: addForm.value.stock_name,
      buy_price: addForm.value.buy_price,
      quantity: addForm.value.quantity,
      buy_reason: addForm.value.buy_reason,
    })
    showAddDialog.value = false
    addForm.value = { stock_code: '', stock_name: '', buy_price: 0, quantity: 100, buy_reason: '' }
    await refreshAll()
  } catch (e) {
    console.error('Failed to add position:', e)
  } finally {
    submitting.value = false
  }
}

async function submitSell() {
  if (!sellTarget.value) return
  submitting.value = true
  try {
    await put(`/api/portfolio/holdings/${sellTarget.value.stock_code}/sell`, {
      portfolio_type: activePortfolio.value,
      sell_price: sellForm.value.sell_price,
      sell_reason: sellForm.value.sell_reason,
    })
    showSellDialog.value = false
    sellTarget.value = null
    await refreshAll()
  } catch (e) {
    console.error('Failed to sell position:', e)
  } finally {
    submitting.value = false
  }
}

function handleReset() {
  ElMessageBox.confirm(
    `Reset all positions in ${PORTFOLIO_CONFIGS[activePortfolio.value].label}?`,
    'Reset Portfolio',
    {
      confirmButtonText: 'Reset',
      cancelButtonText: 'Cancel',
      type: 'warning',
      distinguishCancelAndClose: true,
    }
  ).then(async () => {
    try {
      await post('/api/portfolio/reset', { portfolio_type: activePortfolio.value })
      await refreshAll()
    } catch (e) {
      console.error('Failed to reset portfolio:', e)
    }
  }).catch(() => {})
}

// ECharts NAV Chart
function initNavChart() {
  if (!navChartRef.value) return
  if (chartInstance) {
    chartInstance.dispose()
  }
  chartInstance = echarts.init(navChartRef.value)
  updateNavChart()
}

function updateNavChart() {
  if (!chartInstance) return
  const data = nav.value
  if (!data || data.length === 0) {
    chartInstance.clear()
    chartInstance.setOption({
      title: {
        text: 'No NAV data yet',
        textStyle: { color: '#999', fontSize: 13 },
        left: 'center',
        top: 'center',
      },
    })
    return
  }
  chartInstance.setOption({
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(255,255,255,0.95)',
      borderWidth: 0,
      textStyle: { fontSize: 12, fontFamily: 'JetBrains Mono, monospace' },
      formatter: (params: any) => {
        const p = params[0]
        if (!p) return ''
        const d = data[p.dataIndex]
        return `
          <div class="mono">
            <div>${d.date}</div>
            <div style="font-weight:600;margin-top:4px">AUM: ${d.total_asset.toLocaleString()}</div>
            <div>Cash: ${d.cash.toLocaleString()}</div>
            ${d.daily_return_pct !== undefined ? `<div>Daily: ${(d.daily_return_pct >= 0 ? '+' : '')}${d.daily_return_pct.toFixed(2)}%</div>` : ''}
          </div>
        `
      },
    },
    grid: { left: 60, right: 20, top: 20, bottom: 30 },
    xAxis: {
      type: 'category',
      data: data.map(d => d.date),
      axisLine: { lineStyle: { color: '#e0e0e0' } },
      axisLabel: { color: '#999', fontSize: 11, fontFamily: 'JetBrains Mono, monospace' },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#f0f0f0', type: 'dashed' } },
      axisLabel: {
        color: '#999',
        fontSize: 11,
        fontFamily: 'JetBrains Mono, monospace',
        formatter: (v: number) => v >= 10000 ? (v / 10000).toFixed(0) + 'w' : v.toFixed(0),
      },
    },
    series: [{
      type: 'line',
      data: data.map(d => d.total_asset),
      smooth: true,
      symbol: 'none',
      lineStyle: { width: 2, color: '#2b6de5' },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(43, 109, 229, 0.15)' },
          { offset: 1, color: 'rgba(43, 109, 229, 0.01)' },
        ]),
      },
    }],
  })
}

// Watchers
watch(nav, () => {
  nextTick(() => updateNavChart())
})

watch(activePortfolio, () => {
  nextTick(() => refreshAll())
})

// Lifecycle
onMounted(async () => {
  await refreshAll()
  nextTick(() => initNavChart())

  // Auto-refresh every 30s
  refreshTimer = setInterval(() => {
    store.fetchHoldings(activePortfolio.value)
  }, 30000)
})

onUnmounted(() => {
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
})
</script>

<style lang="scss" scoped>
.portfolio-container {
  .mono {
    font-family: 'JetBrains Mono', monospace;
  }
}
</style>
