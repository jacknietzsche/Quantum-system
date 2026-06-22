<template>
  <div class="dashboard-container" v-loading="loading" element-loading-text="加载中...">
    <!-- 顶部状态栏 -->
    <div class="page-header">
      <div class="header-left">
        <h1 class="page-title">
          <span class="title-accent">AShare</span><span class="title-dim">-X</span>
        </h1>
        <div class="header-meta">
          <span class="stat-dot" style="background: var(--accent-green)" />
          <span class="meta-text">DASHBOARD</span>
          <span class="meta-divider" />
          <span class="meta-text">{{ sysStatus?.database?.total_stocks || 0 }} stocks</span>
        </div>
      </div>
      <div class="header-right">
        <el-button size="small" :icon="Refresh" text @click="forceRefresh" :disabled="loading" title="刷新诊断">
          {{ lastUpdate }}
        </el-button>
      </div>
    </div>

    <!-- 市场态势 + AI认知简报 -->
    <div class="regime-card" :style="regimeCardStyle">
      <div class="regime-header">
        <div class="regime-badge" :style="{ background: regimeStyle.bg, borderColor: regimeStyle.border }">
          <span class="regime-dot" :style="{ background: regimeStyle.border }" />
          <span class="regime-label" :style="{ color: regimeStyle.text }">{{ regimeStyle.label }}</span>
        </div>
        <div class="regime-stats">
          <span>Confidence <strong>{{ confidence }}%</strong></span>
          <span class="stat-sep" />
          <span>Score <strong>{{ market?.total_score?.toFixed(2) }}</strong></span>
          <span class="stat-sep" />
          <span>Risk <strong :style="{ color: riskColor }">{{ riskLevel }}</strong></span>
        </div>
      </div>

      <!-- AI认知简报 + Agent健康度 双栏 -->
      <div class="ai-insight-row">
        <div class="ai-brief">
          <div class="ai-brief-header">
            <el-icon :size="14" style="color: var(--accent-cyan)"><Cpu /></el-icon>
            <span>AI认知简报</span>
          </div>
          <div class="ai-summary-text" v-if="marketState">
            "{{ marketState.summary }}"
          </div>
          <div class="ai-summary-text placeholder" v-else>
            "加载市场认知..."
          </div>
          <div v-if="marketState" class="strategy-weights">
            <div class="sw-bar" v-for="sw in strategyWeightBars" :key="sw.key">
              <span class="sw-label" :style="{ color: sw.color }">{{ sw.label }}</span>
              <div class="sw-track">
                <div class="sw-fill" :style="{ background: sw.color, width: sw.pct + '%' }" />
              </div>
              <span class="sw-pct">{{ sw.pct }}%</span>
              <span class="sw-desc" style="color: var(--text-muted); font-size: 10px; margin-left: 4px;">{{ sw.desc }}</span>
            </div>
          </div>
        </div>
        <div class="agent-health">
          <div class="agent-health-header">
            <el-icon :size="14" style="color: var(--accent-purple)"><UserFilled /></el-icon>
            <span>Agent健康度</span>
            <span class="agent-health-hint">准确率</span>
          </div>
          <div v-if="agentHealth?.agents?.length" class="agent-table">
            <div class="agent-row header">
              <span class="agent-name">Agent</span>
              <span class="agent-acc">7d</span>
              <span class="agent-acc">30d</span>
              <span class="agent-acc">全部</span>
              <span class="agent-picks">推荐</span>
            </div>
            <div v-for="a in agentHealth.agents.slice(0, 6)" :key="a.name" class="agent-row">
              <span class="agent-name">{{ a.display_name }}</span>
              <span class="agent-acc" :class="accClass(a.accuracy_7d)">{{ (a.accuracy_7d * 100).toFixed(0) }}%</span>
              <span class="agent-acc" :class="accClass(a.accuracy_30d)">{{ (a.accuracy_30d * 100).toFixed(0) }}%</span>
              <span class="agent-acc" :class="accClass(a.accuracy_all)">{{ (a.accuracy_all * 100).toFixed(0) }}%</span>
              <span class="agent-picks" style="color: var(--text-muted)">{{ a.total_picks }}</span>
            </div>
          </div>
          <div v-else class="agent-empty">
            <span style="color: var(--text-muted); font-size: 11px;">暂无Agent数据</span>
          </div>
        </div>
      </div>

      <div class="regime-params">
        <span class="param">Position: {{ (market?.adaptive_params?.target_position_pct || 0.5) * 100 }}% target</span>
        <span class="param-sep" />
        <span class="param">Max {{ market?.adaptive_params?.max_holdings || '-' }} holdings</span>
      </div>
    </div>

    <!-- 市场总览 -->
    <div class="market-overview">
      <div class="mo-header">
        <el-icon :size="14" style="color: var(--accent-blue)"><Histogram /></el-icon>
        <span>市场总览</span>
        <span class="mo-tag" v-if="marketState?.timestamp" style="margin-left: auto; font-size: 11px; color: var(--text-muted)">
          诊断: {{ marketState.timestamp }}
        </span>
      </div>
      <div class="mo-body">
        <div class="index-grid">
          <div class="index-item">
            <span class="index-name">上涨</span>
            <span class="index-price" style="color: var(--accent-green)">{{ marketState?.details?.breadth?.up || '--' }}</span>
            <span class="index-chg">>2%</span>
          </div>
          <div class="index-item">
            <span class="index-name">下跌</span>
            <span class="index-price" style="color: var(--accent-red)">{{ marketState?.details?.breadth?.down || '--' }}</span>
            <span class="index-chg">>2%</span>
          </div>
          <div class="index-item">
            <span class="index-name">涨停</span>
            <span class="index-price" style="color: var(--accent-green)">{{ marketState?.details?.breadth?.limit_up || '--' }}</span>
            <span class="index-chg" :style="{ color: marketState?.details?.breadth?.limit_up > 50 ? 'var(--accent-green)' : 'var(--text-muted)' }">
              {{ marketState?.details?.breadth?.limit_up > 50 ? '🔥' : '' }}
            </span>
          </div>
          <div class="index-item">
            <span class="index-name">跌停</span>
            <span class="index-price" style="color: var(--accent-red)">{{ marketState?.details?.breadth?.limit_down || '--' }}</span>
            <span class="index-chg">--</span>
          </div>
        </div>
        <!-- 板块热度 -->
        <div class="sector-row" v-if="marketState?.details?.sectors?.top?.length">
          <span class="sector-label">最强板块</span>
          <span class="sector-tag" v-for="s in marketState.details.sectors.top.slice(0,3)" :key="s.name">
            {{ s.name }} <span style="color: var(--accent-green)">{{ s.change > 0 ? '+' : '' }}{{ s.change }}%</span>
          </span>
        </div>
      </div>
    </div>

    <!-- 四指标卡片 -->
    <div class="metric-grid">
      <div class="metric-card" :style="{ borderLeftColor: riskColor }">
        <div class="metric-label">Risk</div>
        <div class="metric-value" :style="{ color: riskColor }">
          <el-icon :size="18"><WarningFilled v-if="risk?.kill_switch?.active" /><ShieldCheck v-else /></el-icon>
          {{ risk?.kill_switch?.active ? 'BREACHED' : risk ? 'NOMINAL' : '--' }}
        </div>
        <div class="metric-sub">
          P&amp;L {{ risk?.kill_switch?.daily_pnl_pct !== undefined ? (risk.kill_switch.daily_pnl_pct + '%') : '--' }}
        </div>
      </div>
      <div class="metric-card" style="border-left-color: var(--accent-blue)">
        <div class="metric-label">Strategy</div>
        <div class="metric-value" style="color: var(--accent-blue)">
          <el-icon :size="18"><TrendCharts /></el-icon>
          {{ signals?.position_advice?.selection_threshold || (signals ? '--' : '--') }}
        </div>
        <div class="metric-sub">Max {{ signals?.position_advice?.max_holdings || (signals ? '--' : '--') }} holdings</div>
      </div>
      <div class="metric-card" style="border-left-color: var(--accent-cyan)">
        <div class="metric-label">Factors</div>
        <div class="metric-value" style="color: var(--accent-cyan)">
          <el-icon :size="18"><DataLine /></el-icon>
          {{ signals?.top_factors?.length ? signals.top_factors.length : (signals ? '0' : '--') }} <span class="metric-unit">Active</span>
        </div>
        <div class="metric-sub">IC &gt; 0.03</div>
      </div>
      <div class="metric-card" :style="{ borderLeftColor: qualityColor }">
        <div class="metric-label">Data Quality</div>
        <div class="metric-value" :style="{ color: qualityColor }">
          <el-icon :size="18"><Coin /></el-icon>
          {{ quality !== undefined && quality !== null ? quality : '--' }}<span class="metric-unit" v-if="quality !== undefined && quality !== null">%</span>
        </div>
        <div class="metric-sub">{{ db?.total_stocks || (db ? '0' : '--') }} stocks</div>
      </div>
    </div>

    <!-- 数据管道状态 -->
    <div v-if="sysStatus?.data_sources && Object.keys(sysStatus.data_sources).length > 0" class="sources-card">
      <div class="sources-header">
        <span>数据管道</span>
        <span class="sources-sub" style="color: var(--text-muted)">{{ onlineSources }}/{{ totalSources }} 可用</span>
      </div>
      <div class="sources-body">
        <div v-for="(s, name) in sysStatus.data_sources" :key="name" class="source-pill" :class="sourceClass(s.state)">
          <span class="source-dot" :class="sourceDotClass(s.state)" />
          <span class="source-name" :style="{ color: sourceTextColor(s.state) }">{{ name }}</span>
          <span v-if="s.failures > 0" class="source-failures">{{ s.failures }}f</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { get } from '@/api/request'
import { aiApi, screeningApi } from '@/api/ai'
import { WarningFilled, CircleCheck, TrendCharts, DataLine, Coin, DataAnalysis, Cpu, UserFilled, Histogram, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const market = ref<any>(null)
const risk = ref<any>(null)
const signals = ref<any>(null)
const sysStatus = ref<any>(null)
const marketState = ref<any>(null)
const agentHealth = ref<any>(null)
const lastUpdate = ref(new Date().toLocaleTimeString())
const loading = ref(true)

const regime = computed(() => marketState.value?.state || market.value?.regime || 'SHOCK')
const confidence = computed(() => Math.round((marketState.value?.confidence || 0.5) * 100))
const db = computed(() => sysStatus.value?.database || {})
const quality = computed(() => db.value?.completeness_pct || 0)

const riskColor = computed(() =>
  risk.value?.kill_switch?.active ? 'var(--accent-red)' : 'var(--accent-green)'
)

const qualityColor = computed(() => {
  const q = quality.value
  if (q >= 80) return 'var(--accent-green)'
  if (q >= 50) return 'var(--accent-amber)'
  return 'var(--accent-red)'
})

const riskLevel = computed(() => {
  const r = regime.value
  if (r === 'PANIC') return 'EXTREME'
  if (r === 'BEAR') return 'HIGH'
  if (r === 'OVERHEAT') return 'ELEVATED'
  if (r === 'DIVERGENCE') return 'MEDIUM'
  return 'LOW'
})

const regimeStyle = computed(() => {
  const styles: Record<string, any> = {
    BULL: { border: '#10b981', bg: 'rgba(16,185,129,0.06)', text: '#10b981', label: 'BULL 强势上行' },
    BEAR: { border: '#ef4444', bg: 'rgba(239,68,68,0.06)', text: '#ef4444', label: 'BEAR 弱势下行' },
    SHOCK: { border: '#f59e0b', bg: 'rgba(245,158,11,0.06)', text: '#f59e0b', label: 'SHOCK 震荡分化' },
    VOLATILE: { border: '#8b5cf6', bg: 'rgba(139,92,246,0.08)', text: '#8b5cf6', label: 'VOLATILE 高波动' },
    PANIC: { border: '#ef4444', bg: 'rgba(239,68,68,0.10)', text: '#ef4444', label: 'PANIC' },
    OVERHEAT: { border: '#f59e0b', bg: 'rgba(245,158,11,0.06)', text: '#f59e0b', label: 'OVERHEATED' },
    DIVERGENCE: { border: '#8b5cf6', bg: 'rgba(139,92,246,0.06)', text: '#8b5cf6', label: 'DIVERGENCE' },
    NEUTRAL: { border: '#3b82f6', bg: 'rgba(59,130,246,0.04)', text: '#3b82f6', label: 'NEUTRAL' },
  }
  return styles[regime.value] || { border: '#5a6a8a', bg: 'transparent', text: '#5a6a8a', label: regime.value }
})

const regimeCardStyle = computed(() => ({
  borderLeft: `3px solid ${regimeStyle.value.border}`,
  background: regimeStyle.value.bg,
}))

const sourceClass = (s: string) =>
  s === 'closed' ? 'source-ok' : s === 'open' ? 'source-err' : 'source-na'

const sourceDotClass = (s: string) =>
  s === 'closed' ? 'dot-ok' : s === 'open' ? 'dot-err' : 'dot-na'

const sourceTextColor = (s: string) =>
  s === 'closed' ? 'var(--accent-green)' : s === 'open' ? 'var(--accent-red)' : 'var(--text-muted)'

const onlineSources = computed(() => {
  if (!sysStatus.value?.data_sources) return 0
  return Object.values(sysStatus.value.data_sources).filter((s: any) => s.state === 'closed').length
})

const totalSources = computed(() => {
  if (!sysStatus.value?.data_sources) return 0
  return Object.keys(sysStatus.value.data_sources).length
})

const strategyWeightBars = computed(() => {
  const w = marketState.value?.weights || {}
  const WEIGHT_LABELS: Record<string, { label: string; color: string; desc: string }> = {
    trend: { label: '趋势质量', color: '#3b82f6', desc: '均线/RSI/MACD' },
    capital: { label: '资金行为', color: '#f59e0b', desc: '量能/换手率' },
    fundamental: { label: 'AI基本面', color: '#10b981', desc: '市值/PE/规则推理' },
    defensive: { label: '防御性', color: '#8b5cf6', desc: '回撤/波动/稳健' },
  }
  return Object.entries(WEIGHT_LABELS).map(([key, meta]) => ({
    key,
    label: meta.label,
    color: meta.color,
    desc: meta.desc,
    pct: Math.round((w[key] || 0.25) * 100),
  }))
})

const accClass = (acc: number) => {
  if (acc >= 0.7) return 'acc-high'
  if (acc >= 0.5) return 'acc-mid'
  return 'acc-low'
}

const loadData = async (forceRefresh = false) => {
  try {
    const results = await Promise.allSettled([
      get('/api/market/regime').catch(() => null),
      get('/api/risk/status').catch(() => null),
      get('/api/signals/today').catch(() => null),
      get('/api/system/status').catch(() => null),
      screeningApi.marketState(forceRefresh).catch(() => null),
      aiApi.getAgentHealth().catch(() => null),
    ])
    const [m, r, s, sys, ms, ah] = results.map(r => r.status === 'fulfilled' ? r.value : null)
    market.value = m
    risk.value = r
    signals.value = s
    sysStatus.value = sys
    marketState.value = ms
    agentHealth.value = ah
    lastUpdate.value = new Date().toLocaleTimeString()

    const fulfilledCount = results.filter(r => r.status === 'fulfilled').length
    if (fulfilledCount < 3) {
      ElMessage.warning(`部分数据加载失败，仅 ${fulfilledCount}/6 个接口正常`)
    }
  } catch (error) {
    console.error('Failed to load dashboard data:', error)
    ElMessage.warning('仪表盘数据加载异常')
  } finally {
    loading.value = false
  }
}

const forceRefresh = () => {
  loading.value = true
  loadData(true)
}

onMounted(() => loadData())
</script>

<style lang="scss" scoped>
.dashboard-container {
  max-width: 960px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

// ── 页面标题 ──
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 20px;
}

.page-title {
  font-size: 20px;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
  margin: 0;
}

.title-accent {
  background: linear-gradient(135deg, var(--accent-blue), var(--accent-cyan));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.title-dim {
  color: var(--text-muted);
  font-weight: 400;
}

.header-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.stat-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.meta-text {
  font-size: 11px;
  font-family: 'JetBrains Mono', monospace;
  color: var(--text-muted);
}

.meta-divider {
  width: 1px;
  height: 10px;
  background: var(--border);
}

.update-time {
  font-size: 11px;
  font-family: 'JetBrains Mono', monospace;
  color: var(--text-muted);
}

// ── 市场态势 ──
.regime-card {
  border-radius: 10px;
  border: 1px solid var(--border);
  padding: 20px;
  transition: all 0.3s;
}

.regime-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 12px;
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
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
  letter-spacing: 1px;
}

.regime-stats {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  font-family: 'JetBrains Mono', monospace;
  color: var(--text-secondary);

  strong {
    font-weight: 600;
  }
}

.stat-sep {
  width: 1px;
  height: 10px;
  background: var(--border);
}

// ── AI认知简报 + Agent健康度 ──
.ai-insight-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 12px;
}

.ai-brief {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px;
}

.ai-brief-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
  font-family: 'JetBrains Mono', monospace;
  margin-bottom: 8px;
}

.ai-summary-text {
  font-size: 15px;
  font-weight: 600;
  color: var(--accent-cyan);
  margin-bottom: 10px;
  line-height: 1.5;

  &.placeholder {
    color: var(--text-muted);
    font-weight: 400;
    font-style: italic;
  }
}

.strategy-weights {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sw-bar {
  display: flex;
  align-items: center;
  gap: 8px;
}

.sw-label {
  width: 28px;
  font-size: 10px;
  font-family: 'JetBrains Mono', monospace;
  font-weight: 600;
}

.sw-track {
  flex: 1;
  height: 6px;
  background: var(--bg-surface);
  border-radius: 3px;
  overflow: hidden;
}

.sw-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.5s ease;
}

.sw-pct {
  width: 36px;
  text-align: right;
  font-size: 10px;
  font-family: 'JetBrains Mono', monospace;
  color: var(--text-muted);
}

.sw-desc {
  display: none;
  font-size: 10px;
  margin-left: 4px;
  color: var(--text-muted);
}
.sw-bar:hover .sw-desc {
  display: inline;
}

// 板块热度
.sector-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  flex-wrap: wrap;
}
.sector-label {
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
}
.sector-tag {
  font-size: 11px;
  background: rgba(255,255,255,0.05);
  padding: 2px 8px;
  border-radius: 4px;
  white-space: nowrap;
}

// Agent健康度
.agent-health {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px;
}

.agent-health-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
  font-family: 'JetBrains Mono', monospace;
  margin-bottom: 8px;
}

.agent-health-hint {
  margin-left: auto;
  font-size: 9px;
  color: var(--text-muted);
}

.agent-table {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.agent-row {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 3px 0;
  font-size: 11px;
  font-family: 'JetBrains Mono', monospace;
  font-weight: 500;

  &.header {
    font-size: 9px;
    color: var(--text-muted);
    letter-spacing: 0.3px;
    border-bottom: 1px solid var(--border);
    padding-bottom: 4px;
    margin-bottom: 2px;
  }

  .agent-name {
    width: 56px;
    color: var(--text-secondary);
    flex-shrink: 0;
  }

  .agent-acc {
    width: 36px;
    text-align: center;
    flex-shrink: 0;

    &.acc-high { color: var(--accent-green); }
    &.acc-mid { color: var(--accent-amber); }
    &.acc-low { color: var(--accent-red); }
  }

  .agent-picks {
    width: 32px;
    text-align: right;
    flex-shrink: 0;
  }
}

.agent-empty {
  padding: 12px 0;
  text-align: center;
}

.regime-params {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.param {
  font-size: 11px;
  font-family: 'JetBrains Mono', monospace;
  color: var(--text-muted);
}

.param-sep {
  width: 3px; height: 3px;
  border-radius: 50%;
  background: var(--text-muted);
  opacity: 0.3;
}

// ── 市场总览 ──
.market-overview {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
}

.mo-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
  font-family: 'JetBrains Mono', monospace;
}

.mo-body {
  padding: 12px 16px;
}

.index-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.index-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 8px;
  background: var(--bg-surface);
  border-radius: 6px;
}

.index-name {
  font-size: 10px;
  font-family: 'JetBrains Mono', monospace;
  color: var(--text-muted);
}

.index-price {
  font-size: 16px;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
  color: var(--text-muted);
}

.index-chg {
  font-size: 12px;
  font-family: 'JetBrains Mono', monospace;
  color: var(--text-muted);
}

// ── 四指标 ──
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
  padding: 16px;
  transition: border-color 0.25s, box-shadow 0.25s;

  &:hover {
    border-color: var(--border-glow);
    box-shadow: var(--shadow-elevated);
  }
}

.metric-label {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 1px;
  font-family: 'JetBrains Mono', monospace;
  color: var(--text-muted);
  margin-bottom: 10px;
}

.metric-value {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 18px;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
}

.metric-unit {
  font-size: 12px;
  font-weight: 400;
  opacity: 0.7;
}

.metric-sub {
  font-size: 11px;
  font-family: 'JetBrains Mono', monospace;
  color: var(--text-secondary);
  margin-top: 6px;
}

// ── 数据源 ──
.sources-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
}

.sources-header {
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  font-size: 11px;
  font-family: 'JetBrains Mono', monospace;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.sources-body {
  padding: 12px 16px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.source-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-radius: 20px;
  font-size: 11px;
  font-family: 'JetBrains Mono', monospace;

  &.source-ok {
    background: rgba(16, 185, 129, 0.08);
    border: 1px solid rgba(16, 185, 129, 0.15);
  }

  &.source-err {
    background: rgba(239, 68, 68, 0.08);
    border: 1px solid rgba(239, 68, 68, 0.15);
  }

  &.source-na {
    background: var(--bg-surface);
    border: 1px solid var(--border);
  }
}

.source-dot {
  width: 6px; height: 6px;
  border-radius: 50%;

  &.dot-ok { background: var(--accent-green); }
  &.dot-err { background: var(--accent-red); }
  &.dot-na { background: var(--text-muted); }
}

.source-failures {
  font-size: 9px;
  color: var(--accent-red);
  background: rgba(239, 68, 68, 0.08);
  padding: 0 4px;
  border-radius: 3px;
}

// ── 响应式 ──
@media (max-width: 768px) {
  .ai-insight-row {
    grid-template-columns: 1fr;
  }

  .metric-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .index-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
