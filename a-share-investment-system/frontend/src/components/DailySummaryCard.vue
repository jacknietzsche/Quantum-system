<template>
  <div v-if="summary" class="daily-summary-card">
    <div class="daily-header">
      <div class="daily-title">
        <el-icon :size="14"><Calendar /></el-icon>
        <span>Daily Analysis</span>
        <span class="daily-date">{{ summary.date }}</span>
      </div>
      <el-button size="small" type="primary" @click="$emit('run-screening')">
        <el-icon><VideoPlay /></el-icon>
        Run Screening
      </el-button>
    </div>
    <div class="daily-body">
      <div class="daily-grid">
        <div class="daily-item">
          <span class="daily-label">Market</span>
          <span class="daily-value" :style="{ color: regimeColor }">{{ summary.market_regime || '?' }}</span>
        </div>
        <div class="daily-item">
          <span class="daily-label">Risk</span>
          <span class="daily-value" :style="{ color: riskColor }">{{ summary.risk_level || '?' }}</span>
        </div>
        <div class="daily-item">
          <span class="daily-label">Recommendations</span>
          <span class="daily-value" style="color: var(--accent-blue)">{{ summary.recommendations_count || 0 }}</span>
        </div>
        <div class="daily-item">
          <span class="daily-label">Positions</span>
          <span class="daily-value" style="color: var(--accent-cyan)">{{ summary.position_count || 0 }}</span>
        </div>
      </div>
      <div v-if="summary.top_recommendations?.length" class="daily-recs">
        <div class="daily-recs-title">Top Picks</div>
        <div v-for="rec in (summary.top_recommendations || []).slice(0, 5)" :key="rec.stock_code" class="daily-rec-item">
          <span class="rec-code">{{ rec.stock_code }}</span>
          <span class="rec-name">{{ rec.stock_name }}</span>
          <span class="rec-signal" :style="{ color: signalColor(rec.signal) }">{{ rec.signal }}</span>
          <span class="rec-score">{{ rec.score }}pts</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Calendar, VideoPlay } from '@element-plus/icons-vue'

interface Recommendation {
  stock_code: string
  stock_name: string
  signal: string
  score: number
}

interface DailySummary {
  date: string
  market_regime?: string
  risk_level?: string
  recommendations_count?: number
  position_count?: number
  top_recommendations?: Recommendation[]
}

const props = defineProps<{ summary: DailySummary | null }>()
defineEmits<{ 'run-screening': [] }>()

const regimeColor = computed(() => {
  const r = props.summary?.market_regime
  if (r === 'BULL') return 'var(--accent-green)'
  if (r === 'BEAR' || r === 'PANIC') return 'var(--accent-red)'
  if (r === 'OVERHEAT') return 'var(--accent-amber)'
  return 'var(--text-muted)'
})

const riskColor = computed(() => {
  const r = props.summary?.risk_level
  if (r === 'HIGH') return 'var(--accent-red)'
  if (r === 'LOW') return 'var(--accent-green)'
  return 'var(--accent-amber)'
})

function signalColor(signal: string): string {
  if (signal === '买入') return 'var(--accent-green)'
  if (signal === '卖出') return 'var(--accent-red)'
  return 'var(--accent-amber)'
}
</script>

<style lang="scss" scoped>
.daily-summary-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 16px;
  transition: border-color 0.25s, box-shadow 0.25s;

  &:hover {
    border-color: var(--border-glow);
    box-shadow: var(--shadow-elevated);
  }
}

.daily-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.daily-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
}

.daily-date {
  font-size: 10px;
  font-family: 'JetBrains Mono', monospace;
  color: var(--text-muted);
  font-weight: 400;
}

.daily-body {
  // spacing handled by children
}

.daily-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 12px;
}

.daily-item {
  text-align: center;
  padding: 8px;
  border-radius: 8px;
  background: rgba(19, 26, 43, 0.4);
  border: 1px solid rgba(30, 45, 74, 0.3);
}

.daily-label {
  display: block;
  font-size: 10px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 4px;
  font-family: 'JetBrains Mono', monospace;
}

.daily-value {
  font-size: 16px;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
}

.daily-recs-title {
  font-size: 10px;
  color: var(--text-muted);
  margin-bottom: 6px;
  font-family: 'JetBrains Mono', monospace;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.daily-rec-item {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 5px 8px;
  font-size: 12px;
  border-radius: 4px;
  transition: background 0.2s;

  &:hover {
    background: rgba(59, 130, 246, 0.04);
  }

  + .daily-rec-item {
    border-top: 1px solid rgba(30, 45, 74, 0.2);
  }
}

.rec-code {
  font-family: 'JetBrains Mono', monospace;
  color: var(--accent-blue);
  min-width: 60px;
}

.rec-name {
  flex: 1;
  color: var(--text-primary);
}

.rec-signal {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 600;
  min-width: 40px;
  text-align: center;
}

.rec-score {
  font-family: 'JetBrains Mono', monospace;
  color: var(--text-muted);
  min-width: 50px;
  text-align: right;
}

@media (max-width: 768px) {
  .daily-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
