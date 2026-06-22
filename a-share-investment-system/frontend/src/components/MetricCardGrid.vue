<template>
  <div class="metric-grid">
    <div class="metric-card" :style="{ borderLeftColor: riskColor }">
      <div class="metric-label">Risk</div>
      <div class="metric-value" :style="{ color: riskColor }">
        <el-icon :size="18"><WarningFilled v-if="riskActive" /><CircleCheck v-else /></el-icon>
        {{ riskActive ? 'BREACHED' : 'NOMINAL' }}
      </div>
      <div class="metric-sub">P&amp;L {{ dailyPnl }}%</div>
    </div>
    <div class="metric-card" style="border-left-color: var(--accent-blue)">
      <div class="metric-label">Strategy</div>
      <div class="metric-value" style="color: var(--accent-blue)">
        <el-icon :size="18"><TrendCharts /></el-icon>
        {{ threshold }}
      </div>
      <div class="metric-sub">Max {{ maxHoldings }} holdings</div>
    </div>
    <div class="metric-card" style="border-left-color: var(--accent-cyan)">
      <div class="metric-label">Factors</div>
      <div class="metric-value" style="color: var(--accent-cyan)">
        <el-icon :size="18"><DataLine /></el-icon>
        {{ factorCount }} <span class="metric-unit">Active</span>
      </div>
      <div class="metric-sub">IC &gt; 0.03</div>
    </div>
    <div class="metric-card" :style="{ borderLeftColor: qualityColor }">
      <div class="metric-label">Data Quality</div>
      <div class="metric-value" :style="{ color: qualityColor }">
        <el-icon :size="18"><Coin /></el-icon>
        {{ quality }}<span class="metric-unit">%</span>
      </div>
      <div class="metric-sub">{{ totalStocks }} stocks</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { WarningFilled, CircleCheck, TrendCharts, DataLine, Coin } from '@element-plus/icons-vue'

const props = defineProps<{
  risk?: { kill_switch?: { active?: boolean; daily_pnl_pct?: number } }
  signals?: { position_advice?: { selection_threshold?: string; max_holdings?: number }; top_factors?: any[] }
  quality?: number
  totalStocks?: number
}>()

const riskActive = computed(() => props.risk?.kill_switch?.active ?? false)
const dailyPnl = computed(() => props.risk?.kill_switch?.daily_pnl_pct ?? 0)
const threshold = computed(() => props.signals?.position_advice?.selection_threshold ?? '--')
const maxHoldings = computed(() => props.signals?.position_advice?.max_holdings ?? '--')
const factorCount = computed(() => props.signals?.top_factors?.length ?? 0)
const quality = computed(() => props.quality ?? 0)

const riskColor = computed(() =>
  riskActive.value ? 'var(--accent-red)' : 'var(--accent-green)'
)

const qualityColor = computed(() => {
  const q = quality.value
  if (q >= 80) return 'var(--accent-green)'
  if (q >= 50) return 'var(--accent-amber)'
  return 'var(--accent-red)'
})
</script>

<style lang="scss" scoped>
.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.metric-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-left: 3px solid;
  border-radius: 10px;
  padding: 14px 16px;
  transition: border-color 0.25s, box-shadow 0.25s;

  &:hover {
    border-color: var(--border-glow);
    box-shadow: var(--shadow-elevated);
  }
}

.metric-label {
  font-size: 10px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 6px;
  font-family: 'JetBrains Mono', monospace;
}

.metric-value {
  font-size: 20px;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
  display: flex;
  align-items: center;
  gap: 6px;

  .el-icon { flex-shrink: 0; }
}

.metric-unit {
  font-size: 12px;
  font-weight: 400;
  color: var(--text-muted);
  margin-left: 2px;
}

.metric-sub {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 4px;
  font-family: 'JetBrains Mono', monospace;
}

@media (max-width: 768px) {
  .metric-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
