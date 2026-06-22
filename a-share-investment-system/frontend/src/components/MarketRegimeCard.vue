<template>
  <div class="regime-card" :style="cardStyle">
    <div class="regime-header">
      <div class="regime-badge" :style="{ background: style.bg, borderColor: style.border }">
        <span class="regime-dot" :style="{ background: style.border }" />
        <span class="regime-label" :style="{ color: style.text }">{{ style.label }}</span>
      </div>
      <div class="regime-stats">
        <span>Confidence <strong>{{ confidence }}%</strong></span>
        <span class="stat-sep" />
        <span>Score <strong>{{ market?.total_score?.toFixed(2) }}</strong></span>
      </div>
    </div>
    <div class="regime-params">
      <span class="param">Risk: <span :style="{ color: riskColor }">{{ riskLevel }}</span></span>
      <span class="param-sep" />
      <span class="param">Position: {{ (market?.adaptive_params?.target_position_pct || 0.5) * 100 }}% target</span>
      <span class="param-sep" />
      <span class="param">Max {{ market?.adaptive_params?.max_holdings || '-' }} holdings</span>
    </div>
    <div class="dimension-grid">
      <div v-for="(v, k) in market?.dimension_scores || {}" :key="k" class="dimension-item">
        <div class="dim-label">{{ String(k).replace('_', ' ') }}</div>
        <div class="dim-value" :class="v >= 0 ? 'num-up' : 'num-down'">{{ v }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface MarketData {
  regime?: string
  total_score?: number
  adaptive_params?: {
    target_position_pct?: number
    max_holdings?: number
  }
  dimension_scores?: Record<string, number>
}

const props = defineProps<{ market: MarketData | null }>()

const regime = computed(() => props.market?.regime || 'NEUTRAL')
const score = computed(() => Math.abs(props.market?.total_score || 0))
const confidence = computed(() => Math.min(95, Math.round(50 + score.value * 25)))

const riskLevel = computed(() => {
  const r = regime.value
  if (r === 'PANIC') return 'EXTREME'
  if (r === 'BEAR') return 'HIGH'
  if (r === 'OVERHEAT') return 'ELEVATED'
  return 'LOW'
})

const riskColor = computed(() => {
  const r = riskLevel.value
  if (r === 'EXTREME' || r === 'HIGH') return 'var(--accent-red)'
  if (r === 'ELEVATED') return 'var(--accent-amber)'
  return 'var(--accent-green)'
})

const REGIME_STYLES: Record<string, { border: string; bg: string; text: string; label: string }> = {
  BULL: { border: '#10b981', bg: 'rgba(16,185,129,0.06)', text: '#34d399', label: 'BULL MARKET' },
  BEAR: { border: '#ef4444', bg: 'rgba(239,68,68,0.06)', text: '#f87171', label: 'BEAR MARKET' },
  PANIC: { border: '#ef4444', bg: 'rgba(239,68,68,0.10)', text: '#f87171', label: 'PANIC' },
  OVERHEAT: { border: '#f59e0b', bg: 'rgba(245,158,11,0.06)', text: '#fbbf24', label: 'OVERHEATED' },
  NEUTRAL: { border: '#3b82f6', bg: 'rgba(59,130,246,0.04)', text: '#60a5fa', label: 'NEUTRAL' },
}

const style = computed(() =>
  REGIME_STYLES[regime.value] || { border: '#5a6a8a', bg: 'transparent', text: '#8892b0', label: regime.value }
)

const cardStyle = computed(() => ({
  borderLeft: `3px solid ${style.value.border}`,
  background: style.value.bg,
}))
</script>

<style lang="scss" scoped>
.regime-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 20px;
  transition: border-color 0.3s, box-shadow 0.3s;

  &:hover {
    border-color: var(--border-glow);
    box-shadow: var(--shadow-elevated);
  }
}

.regime-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.regime-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 4px 14px;
  border-radius: 20px;
  border: 1px solid;
  font-size: 13px;
}

.regime-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.regime-label {
  font-weight: 600;
  font-family: 'JetBrains Mono', monospace;
  letter-spacing: 1px;
}

.regime-stats {
  font-size: 12px;
  color: var(--text-muted);
  font-family: 'JetBrains Mono', monospace;
  display: flex;
  align-items: center;
  gap: 8px;

  strong {
    color: var(--text-primary);
  }
}

.stat-sep {
  width: 1px;
  height: 10px;
  background: var(--border);
}

.regime-params {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.param {
  font-size: 11px;
  font-family: 'JetBrains Mono', monospace;
  color: var(--text-muted);
}

.param-sep {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: var(--text-muted);
  opacity: 0.3;
}

.dimension-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(80px, 1fr));
  gap: 8px;
}

.dimension-item {
  text-align: center;
  padding: 6px 4px;
  border-radius: 6px;
  background: rgba(19, 26, 43, 0.4);
  border: 1px solid rgba(30, 45, 74, 0.3);
}

.dim-label {
  font-size: 10px;
  color: var(--text-muted);
  text-transform: capitalize;
  margin-bottom: 2px;
  font-family: 'JetBrains Mono', monospace;
}

.dim-value {
  font-size: 14px;
  font-weight: 600;
  font-family: 'JetBrains Mono', monospace;
}

.num-up { color: var(--accent-green); }
.num-down { color: var(--accent-red); }
</style>
