<template>
  <div class="screening-container">
    <div class="space-y-4 max-w-5xl">
      <!-- ═══ 顶部操作栏 ═══ -->
      <div class="flex justify-between items-center">
        <h1 class="text-lg font-semibold tracking-wide mono" style="color: var(--text-primary)">
          SCREENING
        </h1>
        <div class="flex items-center gap-3">
          <el-select
            v-model="portfolioContext"
            size="small"
            placeholder="Portfolio context"
            style="width: 140px"
          >
            <el-option label="None" value="" />
            <el-option label="🔥 Limit Up" value="limit_up" />
            <el-option label="📈 Momentum" value="momentum" />
            <el-option label="💎 Value" value="value" />
          </el-select>
          <span v-if="elapsed !== null" class="mono text-xs" style="color: var(--accent-green)">
            Done in {{ elapsed }}s
          </span>
          <span v-if="startTime" class="mono text-xs" style="color: var(--text-muted)">
            Started {{ startTime }}
          </span>
          <el-button
            v-if="flowStatus !== 'idle' && flowStatus !== 'complete'"
            type="danger"
            size="small"
            @click="abortScreening"
          >
            STOP
          </el-button>
          <el-button
            type="primary"
            :loading="flowStatus !== 'idle' && flowStatus !== 'complete'"
            @click="runScreening"
          >
            <el-icon v-if="flowStatus === 'idle' || flowStatus === 'complete'"><VideoPlay /></el-icon>
            {{ flowStatus === 'idle' ? 'RUN SCREEN' : flowStatus === 'complete' ? 'RE-RUN' : 'RUNNING...' }}
          </el-button>
        </div>
      </div>

      <el-tabs v-model="activeStyle" @tab-change="onStyleChange" class="style-tabs">
        <el-tab-pane
          v-for="tab in ALL_STYLES" :key="tab.name"
          :label="tab.label" :name="tab.name"
        />
      </el-tabs>

      <!-- ═══ 叙事状态标签 ═══ -->
      <div v-if="flowStatus !== 'idle'" class="narrative-status">
        <span class="ns-dot" :class="'ns-' + flowStatus" />
        <span class="ns-label">{{ statusLabel }}</span>
      </div>

      <!-- ═══ 市场诊断卡片 (醒目) ═══ -->
      <div v-if="narrative.marketState" class="market-diagnosis-card">
        <div class="md-header">
          <el-icon :size="14" style="color: var(--accent-cyan)"><Cpu /></el-icon>
          <span>AI市场诊断</span>
        </div>
        <div class="md-summary">
          "{{ narrative.marketState.summary }}"
        </div>
        <div class="md-meta">
          <span class="md-tag" :style="mdRegimeStyle">
            <span class="md-dot" />
            {{ narrative.marketState.regime }}
          </span>
          <span class="md-tag" style="background: rgba(59,130,246,0.08); color: var(--accent-blue)">
            置信度 {{ (narrative.marketState.confidence * 100).toFixed(0) }}%
          </span>
          <span class="md-tag" :style="mdRiskStyle">
            {{ narrative.marketState.risk_level }}
          </span>
        </div>
      </div>

      <!-- ═══ Agent动议区 (卡片流) ═══ -->
      <div v-if="narrative.agentProposals.length > 0" class="proposals-section">
        <div class="section-header">
          <el-icon :size="14" style="color: var(--accent-purple)"><UserFilled /></el-icon>
          <span>Agent动议</span>
          <span class="section-count">{{ narrative.agentProposals.length }} 条</span>
        </div>
        <div class="proposals-flow">
          <div
            v-for="(p, i) in narrative.agentProposals"
            :key="i"
            class="proposal-card"
            @click="toggleProposal(i)"
          >
            <div class="pc-header">
              <span class="pc-agent-icon">{{ agentIcon(p.agent_name) }}</span>
              <div class="pc-agent-info">
                <span class="pc-agent-name">{{ p.display_name || p.agent_name }}</span>
                <span class="pc-meta">{{ p.recommend_count }} 只推荐</span>
              </div>
              <el-icon class="pc-chevron" :class="{ rotated: expandedProposal === i }">
                <ArrowDown />
              </el-icon>
            </div>
            <div class="pc-logic">{{ p.logic_summary }}</div>
            <div v-if="expandedProposal === i && p.stock_codes?.length" class="pc-stocks">
              <span v-for="code in p.stock_codes" :key="code" class="pc-stock-tag">
                {{ code }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- ═══ 阶段进度卡片 (始终显示) ═══ -->
      <div class="stage-grid">
        <div
          v-for="(s, i) in stages" :key="i"
          class="stage-card"
          :class="'stage-' + s.status"
          @click="showStageDetail(i)"
        >
          <div class="stage-dot" />
          <div class="stage-info">
            <div class="stage-name">{{ s.name }}</div>
            <div class="stage-metrics" v-if="s.metrics">
              <span v-for="(v, k) in s.metrics" :key="k" class="stage-metric">
                {{ k }}: {{ v }}
              </span>
            </div>
          </div>
          <div class="stage-icon">
            <el-icon v-if="s.status === 'done'" style="color: var(--accent-green)"><CircleCheck /></el-icon>
            <el-icon v-else-if="s.status === 'failed'" style="color: var(--accent-red)"><WarningFilled /></el-icon>
            <el-icon v-else-if="s.status === 'running'" class="is-loading" style="color: var(--accent-blue)"><Loading /></el-icon>
          </div>
        </div>
      </div>

      <!-- ═══ 辩论裁决面板 ═══ -->
      <div v-if="narrative.debateRounds.length > 0" class="debate-section">
        <div class="section-header">
          <el-icon :size="14" style="color: var(--accent-amber)"><ChatDotSquare /></el-icon>
          <span>辩论裁决</span>
          <span class="section-count">{{ narrative.debateRounds.length }} 轮</span>
        </div>
        <div v-for="(round, ri) in narrative.debateRounds" :key="ri" class="debate-round">
          <div class="dr-header">
            <span class="dr-issue">{{ round.key_issue }}</span>
            <span class="dr-stock" v-if="round.stock_code">{{ round.stock_code }}</span>
          </div>
          <div class="dr-args">
            <div class="dr-pro">
              <div class="dr-label pro">多方</div>
              <div class="dr-text">{{ round.pro_args }}</div>
            </div>
            <div class="dr-con">
              <div class="dr-label con">空方</div>
              <div class="dr-text">{{ round.con_args }}</div>
            </div>
          </div>
          <div class="dr-verdict" v-if="round.verdict">
            <span class="dr-vlabel">AI裁决:</span>
            <span :style="{ color: round.verdict.includes('采纳多方') ? 'var(--accent-green)' : round.verdict.includes('采纳空方') ? 'var(--accent-red)' : 'var(--accent-amber)' }">
              {{ round.verdict }}
            </span>
          </div>
        </div>
      </div>

      <!-- ═══ 最终推荐表格 ═══ -->
      <div v-if="recommendations.length > 0" class="card p-0 overflow-hidden">
        <div class="rec-header">
          <span class="rec-title">最终推荐</span>
          <span class="rec-count">{{ recommendations.length }} 只股票</span>
        </div>
        <el-table
          :data="visibleRecommendations"
          style="width: 100%"
          size="small"
          stripe
          @row-click="handleRowClick"
        >
          <el-table-column label="#" prop="rank" width="44" align="center">
            <template #default="{ row }">
              <span class="mono text-xs" :style="{ color: row.rank <= 3 ? 'var(--accent-amber)' : 'var(--text-muted)' }">{{ row.rank }}</span>
            </template>
          </el-table-column>
          <el-table-column label="Code" width="85">
            <template #default="{ row }">
              <span class="mono text-sm" style="color: var(--accent-blue)">{{ row.stock_code }}</span>
            </template>
          </el-table-column>
          <el-table-column label="Name" prop="stock_name" width="80" show-overflow-tooltip />
          <el-table-column label="Score" width="50" align="right">
            <template #default="{ row }">
              <span class="mono font-bold" :style="{ color: stageColor }">{{ row.score }}</span>
            </template>
          </el-table-column>
          <el-table-column label="Signal" width="70" align="center">
            <template #default="{ row }">
              <span class="badge text-xs" :class="signalClass(row.signal)">{{ row.signal }}</span>
            </template>
          </el-table-column>
          <el-table-column label="Agent共识" width="90" align="center">
            <template #default="{ row }">
              <span class="mono text-xs" style="color: var(--text-secondary)">
                {{ row.supporting_agents?.length || row.masters_used?.length || 0 }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="逻辑摘要" min-width="140" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="mono text-xs" style="color: var(--text-secondary)">{{ row.logic_summary || row.reasoning || row.reason || '--' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="辩论" width="80" align="center">
            <template #default="{ row }">
              <span v-if="row.debate_report?.verdict" class="badge text-xs" :class="row.debate_report.verdict === '维持推荐' ? 'badge-up' : 'badge-warn'">
                通过
              </span>
              <span v-else-if="row.stage4_analyzed" class="badge text-xs" :class="verdictBadgeClass(row.stage4_verdict)">
                {{ row.stage4_verdict || '—' }}
              </span>
              <span v-else class="text-xs" style="color: var(--text-muted)">—</span>
            </template>
          </el-table-column>
          <el-table-column label="仓位" width="60" align="center">
            <template #default="{ row }">
              <span v-if="row.position_suggestion" class="mono text-xs" style="color: var(--accent-green)">
                {{ row.position_suggestion }}
              </span>
              <span v-else class="text-xs" style="color: var(--text-muted)">—</span>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="recommendations.length > PAGE_SIZE" class="flex justify-center py-3">
          <el-pagination
            v-model:current-page="page"
            :page-size="PAGE_SIZE"
            :total="recommendations.length"
            layout="prev, pager, next"
            small
          />
        </div>
      </div>

      <!-- 空状态 -->
      <div
        v-if="flowStatus === 'idle'"
        class="text-center py-20 mono text-sm"
        style="color: var(--text-muted)"
      >
        Press RUN SCREEN to activate AI screening narrative
      </div>
      <div
        v-if="flowStatus === 'complete' && recommendations.length === 0"
        class="empty-state text-center py-10"
      >
        <el-icon :size="36" style="color: var(--text-muted)"><WarningFilled /></el-icon>
        <div class="empty-title mono text-sm" style="color: var(--accent-red)">无符合条件股票</div>
        <div class="empty-desc mono text-xs" style="color: var(--text-muted); margin-top: 8px;">
          数据不完整 / 过滤条件过于严格 / 今日无候选
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onUnmounted } from 'vue'
import { get, post } from '@/api/request'
import { VideoPlay, Cpu, UserFilled, ChatDotSquare, CircleCheck, WarningFilled, Loading, ArrowDown } from '@element-plus/icons-vue'
import { ALL_STYLES, STYLE_CONFIGS } from '@/types/screening'
import type { ScreenStyle, ScreeningData } from '@/types/screening'

const PAGE_SIZE = 20
let eventSource: EventSource | null = null
let pollTimer: ReturnType<typeof setInterval> | null = null

// ── Types ──
interface MarketDiagnosis {
  summary: string
  confidence: number
  regime: string
  risk_level: string
  strategy_weights?: Record<string, number>
}

interface AgentProposal {
  agent_name: string
  display_name?: string
  recommend_count: number
  logic_summary: string
  stock_codes?: string[]
}

interface DebateRound {
  key_issue: string
  stock_code?: string
  pro_args: string
  con_args: string
  verdict?: string
}

type FlowStatus = 'idle' | 'diagnosing' | 'proposing' | 'debating' | 'complete'

interface NarrativeState {
  marketState: MarketDiagnosis | null
  agentProposals: AgentProposal[]
  debateRounds: DebateRound[]
}

// ── State ──
const activeStyle = ref<ScreenStyle>('hybrid')
const flowStatus = ref<FlowStatus>('idle')
const narrative = reactive<NarrativeState>({
  marketState: null,
  agentProposals: [],
  debateRounds: [],
})
const results = ref<ScreeningData | null>(null)
const elapsed = ref<number | null>(null)
const startTime = ref<string | null>(null)
const page = ref(1)
const portfolioContext = ref('')
const expandedProposal = ref<number | null>(null)
const selectedStock = ref<string | null>(null)

// ── Stage state ──
interface StageState { name: string; status: 'waiting' | 'running' | 'done' | 'failed'; metrics: Record<string, string | number> | null }
const stages = reactive<StageState[]>([
  { name: '市场感知', status: 'waiting', metrics: null },
  { name: '量化筛选', status: 'waiting', metrics: null },
  { name: 'AI分析', status: 'waiting', metrics: null },
  { name: 'AI调参', status: 'waiting', metrics: null },
  { name: '辩论裁决', status: 'waiting', metrics: null },
  { name: '记忆存储', status: 'waiting', metrics: null },
])

const stageColor = computed(() => STYLE_CONFIGS[activeStyle.value].color)
const recommendations = computed(() => results.value?.recommendations ?? [])
const visibleRecommendations = computed(() => {
  const start = (page.value - 1) * PAGE_SIZE
  return recommendations.value.slice(start, start + PAGE_SIZE)
})

const statusLabel = computed(() => {
  const labels: Record<FlowStatus, string> = {
    idle: '就绪',
    diagnosing: 'AI市场诊断中...',
    proposing: 'Agent提交动议...',
    debating: '辩论裁决中...',
    complete: '选股完成',
  }
  return labels[flowStatus.value]
})

const mdRegimeStyle = computed(() => {
  if (!narrative.marketState) return {}
  const r = narrative.marketState.regime
  if (r === 'BULL') return { background: 'rgba(16,185,129,0.08)', color: 'var(--accent-green)' }
  if (r === 'BEAR' || r === 'PANIC') return { background: 'rgba(239,68,68,0.08)', color: 'var(--accent-red)' }
  if (r === 'DIVERGENCE') return { background: 'rgba(139,92,246,0.08)', color: 'var(--accent-purple)' }
  return { background: 'rgba(59,130,246,0.08)', color: 'var(--accent-blue)' }
})

const mdRiskStyle = computed(() => {
  if (!narrative.marketState) return {}
  const l = narrative.marketState.risk_level
  if (l === 'high' || l === 'extreme') return { background: 'rgba(239,68,68,0.08)', color: 'var(--accent-red)' }
  if (l === 'medium') return { background: 'rgba(245,158,11,0.08)', color: 'var(--accent-amber)' }
  return { background: 'rgba(16,185,129,0.08)', color: 'var(--accent-green)' }
})

function agentIcon(name: string): string {
  const icons: Record<string, string> = {
    buffett: '🏦', lynch: '📊', burry: '🛡️', wood: '🚀',
    livermore: '📈', druck: '💼', turtle: '🐢',
    value: '💎', momentum: '📈', limit_up: '🔥',
  }
  return icons[name.toLowerCase()] || '🤖'
}

function toggleProposal(i: number) {
  expandedProposal.value = expandedProposal.value === i ? null : i
}

// ── SSE ──
function cleanup() {
  if (eventSource) { eventSource.close(); eventSource = null }
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

function resetStages() {
  stages.forEach(s => { s.status = 'waiting'; s.metrics = null })
}

function onStyleChange() {
  if (flowStatus.value !== 'idle' && flowStatus.value !== 'complete') {
    post('/api/screening/abort', {}).catch(() => {})
  }
  cleanup()
  elapsed.value = null
  results.value = null
  narrative.marketState = null
  narrative.agentProposals = []
  narrative.debateRounds = []
  flowStatus.value = 'idle'
  resetStages()
}

function abortScreening() {
  post('/api/screening/abort', {}).catch(() => {})
  cleanup()
  flowStatus.value = 'complete'
}

const streamUrl = computed(() => {
  let url = `/api/screening/run/stream?style=${activeStyle.value}`
  if (portfolioContext.value) url += `&portfolio_type=${portfolioContext.value}`
  return url
})

function _detectStageFromLog(msg: string): number {
  if (/Stage0|市场感知|市场环境|market_state/.test(msg)) return 0
  if (/Stage1|Stage2|HardFilter|初筛|量化|基本面/.test(msg)) return 1
  if (/Stage3|大师|deep_analyze|master_analyze|量化大师/.test(msg)) return 2
  if (/Stage3\.5|Orchestrator|调参|评分调整|orchestrator/.test(msg)) return 3
  if (/Stage4|辩论|debate/.test(msg)) return 4
  if (/Stage5|复盘|记忆|memory|保存/.test(msg)) return 5
  return -1
}

function runWithSSE(t0: number) {
  eventSource = new EventSource(streamUrl.value)

  eventSource.addEventListener('market_diagnosis', (event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data)
      narrative.marketState = data as MarketDiagnosis
      flowStatus.value = 'diagnosing'
      stages[0].status = 'done'
    } catch { /* ignore */ }
  })

  eventSource.addEventListener('agent_proposal', (event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data) as AgentProposal
      narrative.agentProposals.push(data)
      flowStatus.value = 'proposing'
      stages[1].status = 'done'
      stages[2].status = 'running'
    } catch { /* ignore */ }
  })

  eventSource.addEventListener('debate_round', (event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data) as DebateRound
      narrative.debateRounds.push(data)
      flowStatus.value = 'debating'
      stages[3].status = 'done'
      stages[4].status = 'running'
    } catch { /* ignore */ }
  })

  eventSource.addEventListener('final_recommendation', (event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data) as ScreeningData
      results.value = data
      elapsed.value = parseFloat(((Date.now() - t0) / 1000).toFixed(1))
      flowStatus.value = 'complete'
      stages[4].status = 'done'
      stages[5].status = 'done'
      cleanup()
    } catch { /* ignore */ }
  })

  // Fallback: handle standard heartbeat/stage events
  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      const msgType = data.type || 'stage'

      if (msgType === 'heartbeat') {
        if (data.logs) {
          for (const log of data.logs) {
            const stageIdx = _detectStageFromLog(log.msg)
            if (stageIdx >= 0 && stageIdx < stages.length) {
              // pass
            }
          }
        }
        if (data.stage !== undefined) {
          const si = data.stage
          for (let i = 0; i < si; i++) {
            if (i < stages.length && stages[i].status !== 'done') stages[i].status = 'done'
          }
          if (si >= 0 && si < stages.length && stages[si].status !== 'done') stages[si].status = 'running'
        }
        return
      }

      if (data.stage !== undefined) {
        const si = data.stage
        if (si >= 0 && si < stages.length) {
          stages[si].status = data.results ? 'done' : 'running'
          if (data.details) {
            stages[si].metrics = Object.fromEntries(
              Object.entries(data.details).filter(([_, v]) => typeof v === 'string' || typeof v === 'number')
            ) as Record<string, string | number>
          }
        }
        for (let i = 0; i < si; i++) {
          if (i < stages.length && stages[i].status !== 'done') stages[i].status = 'done'
        }
      }

      if (data.results) {
        results.value = data.results
        elapsed.value = parseFloat(((Date.now() - t0) / 1000).toFixed(1))
        flowStatus.value = 'complete'
        stages.forEach(s => { if (s.status === 'running') s.status = 'done' })
        cleanup()
      } else if (data.error) {
        flowStatus.value = 'complete'
        cleanup()
      }
    } catch { /* ignore */ }
  }

  eventSource.onerror = () => {
    cleanup()
    if (!results.value) {
      attemptRecovery(t0)
    }
  }
}

async function attemptRecovery(t0: number) {
  try {
    const r: any = await get('/api/screening/results')
    if (r && r.recommendations) {
      results.value = r as ScreeningData
      elapsed.value = parseFloat(((Date.now() - t0) / 1000).toFixed(1))
      flowStatus.value = 'complete'
      stages.forEach(s => { if (s.status === 'running') s.status = 'done' })
      return
    }
  } catch { /* fall through */ }
  try {
    const s: any = await get('/api/screening/status')
    if (s && s.running) {
      runWithPolling(t0)
      return
    }
  } catch { /* fall through */ }
  flowStatus.value = 'complete'
}

async function runWithPolling(t0: number) {
  try {
    await get(`/api/screening/run?style=${activeStyle.value}${portfolioContext.value ? `&portfolio_type=${portfolioContext.value}` : ''}`)
  } catch {
    flowStatus.value = 'complete'
    return
  }

  pollTimer = setInterval(async () => {
    try {
      const s: any = await get('/api/screening/status')
      if (!s.running) {
        const r = await get('/api/screening/results')
        results.value = r as unknown as ScreeningData
        elapsed.value = parseFloat(((Date.now() - t0) / 1000).toFixed(1))
        flowStatus.value = 'complete'
        clearInterval(pollTimer!)
        pollTimer = null
      }
    } catch {
      clearInterval(pollTimer!)
      pollTimer = null
    }
  }, 2000)
}

async function runScreening() {
  cleanup()
  const t0 = Date.now()
  startTime.value = new Date().toLocaleTimeString()
  elapsed.value = null
  results.value = null
  narrative.marketState = null
  narrative.agentProposals = []
  narrative.debateRounds = []
  page.value = 1
  resetStages()
  flowStatus.value = 'diagnosing'

  if (typeof EventSource !== 'undefined') {
    runWithSSE(t0)
  } else {
    runWithPolling(t0)
  }
}

function handleRowClick(row: any) {
  selectedStock.value = row.stock_code
}

function showStageDetail(idx: number) {
  // Stage detail display could be restored from logs
}

const signalClass = (signal: string) => {
  if (signal === '买入' || signal === 'bullish') return 'badge-up'
  if (signal === '卖出' || signal === 'bearish') return 'badge-down'
  return 'badge-warn'
}

const verdictBadgeClass = (verdict: string | undefined) => {
  if (verdict === '买入') return 'badge-up'
  if (verdict === '卖出') return 'badge-down'
  return 'badge-warn'
}

onUnmounted(() => cleanup())
</script>

<style lang="scss" scoped>
.screening-container {
  .mono { font-family: 'JetBrains Mono', monospace; }

  :deep(.el-table .warning-row) { background: rgba(239, 68, 68, 0.03); }
  :deep(.el-table .el-table__row:hover) { cursor: pointer; }
}

// ── 叙事状态 ──
.narrative-status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
}

.ns-dot {
  width: 8px; height: 8px;
  border-radius: 50%;

  &.ns-diagnosing { background: var(--accent-blue); animation: pulse-glow 1.5s infinite; }
  &.ns-proposing { background: var(--accent-purple); animation: pulse-glow 1.5s infinite; }
  &.ns-debating { background: var(--accent-amber); animation: pulse-glow 1.5s infinite; }
  &.ns-complete { background: var(--accent-green); }
}

.ns-label {
  font-size: 12px;
  font-family: 'JetBrains Mono', monospace;
  color: var(--text-secondary);
}

// ── 市场诊断 ──
.market-diagnosis-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-left: 3px solid var(--accent-cyan);
  border-radius: 10px;
  padding: 20px;
}

.md-header {
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

.md-summary {
  font-size: 18px;
  font-weight: 600;
  color: var(--accent-cyan);
  margin-bottom: 10px;
  line-height: 1.5;
}

.md-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.md-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-family: 'JetBrains Mono', monospace;
  font-weight: 600;
}

.md-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: currentColor;
}

// ── Agent动议区 ──
.section-header {
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

.section-count {
  margin-left: auto;
  font-size: 10px;
  color: var(--text-muted);
}

.proposals-flow {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.proposal-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-left: 3px solid var(--accent-purple);
  border-radius: 8px;
  padding: 12px 14px;
  cursor: pointer;
  transition: border-color 0.2s;

  &:hover {
    border-color: var(--border-glow);
  }
}

.pc-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}

.pc-agent-icon {
  font-size: 20px;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-surface);
  border-radius: 6px;
}

.pc-agent-info {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.pc-agent-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.pc-meta {
  font-size: 10px;
  color: var(--text-muted);
  font-family: 'JetBrains Mono', monospace;
}

.pc-chevron {
  font-size: 14px;
  color: var(--text-muted);
  transition: transform 0.2s;

  &.rotated { transform: rotate(180deg); }
}

.pc-logic {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.pc-stocks {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border);
}

.pc-stock-tag {
  font-size: 10px;
  font-family: 'JetBrains Mono', monospace;
  color: var(--accent-blue);
  background: rgba(59, 130, 246, 0.06);
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid rgba(59, 130, 246, 0.12);
}

// ── 阶段卡片 ──
.stage-grid {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.stage-card {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  min-width: 120px;
  flex: 1;
  cursor: pointer;
  transition: border-color 0.2s;

  &:hover { border-color: var(--border-glow); }

  &.stage-running {
    border-color: var(--accent-blue);
    background: rgba(59, 130, 246, 0.03);
  }

  &.stage-done { opacity: 0.8; }
  &.stage-failed { border-color: var(--accent-red); }
}

.stage-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--text-muted);
  flex-shrink: 0;

  .stage-running & { background: var(--accent-blue); animation: pulse-glow 1.5s infinite; }
  .stage-done & { background: var(--accent-green); }
  .stage-failed & { background: var(--accent-red); }
}

.stage-info {
  flex: 1;
  min-width: 0;
}

.stage-name {
  font-size: 11px;
  font-family: 'JetBrains Mono', monospace;
  font-weight: 600;
  color: var(--text-primary);
}

.stage-metrics {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  margin-top: 2px;
}

.stage-metric {
  font-size: 9px;
  font-family: 'JetBrains Mono', monospace;
  color: var(--text-muted);
  background: var(--bg-surface);
  padding: 1px 4px;
  border-radius: 2px;
}

.stage-icon {
  flex-shrink: 0;
  font-size: 14px;
}

// ── 辩论面板 ──
.debate-section {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 16px;
}

.debate-round {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  margin-top: 8px;
}

.dr-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.dr-issue {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.dr-stock {
  font-size: 10px;
  font-family: 'JetBrains Mono', monospace;
  color: var(--accent-blue);
  background: rgba(59, 130, 246, 0.06);
  padding: 1px 6px;
  border-radius: 3px;
  margin-left: auto;
}

.dr-args {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-bottom: 8px;
}

.dr-label {
  font-size: 10px;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
  margin-bottom: 4px;

  &.pro { color: var(--accent-green); }
  &.con { color: var(--accent-red); }
}

.dr-text {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.dr-verdict {
  font-size: 12px;
  font-family: 'JetBrains Mono', monospace;
  color: var(--text-secondary);
  padding-top: 8px;
  border-top: 1px solid var(--border);
}

.dr-vlabel {
  color: var(--text-muted);
  margin-right: 6px;
}

// ── 推荐表头 ──
.rec-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
}

.rec-title {
  font-size: 11px;
  font-weight: 600;
  font-family: 'JetBrains Mono', monospace;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-primary);
}

.rec-count {
  margin-left: auto;
  font-size: 10px;
  color: var(--text-muted);
  font-family: 'JetBrains Mono', monospace;
}

// ── Empty state ──
.empty-state {
  max-width: 400px;
  margin: 0 auto;
}

.empty-title { font-weight: 600; }
</style>
