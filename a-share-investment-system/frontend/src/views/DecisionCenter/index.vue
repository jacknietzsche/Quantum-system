<template>
  <div class="decision-container">
    <!-- 顶部 -->
    <div class="page-header">
      <div class="header-left">
        <h1 class="page-title">
          <span class="title-accent">AI</span><span class="title-dim"> 决策中心</span>
        </h1>
        <div class="header-meta">
          <span class="meta-text">QuantAgent 每日投资决策</span>
        </div>
      </div>
      <div class="header-right">
        <el-button
          :type="running ? 'danger' : 'primary'"
          :icon="running ? 'CircleClose' : 'Cpu'"
          :loading="running"
          @click="toggleRun"
        >
          {{ running ? '停止' : '启动AI决策' }}
        </el-button>
      </div>
    </div>

    <!-- 市场诊断卡片 -->
    <transition name="fade">
      <div v-if="diagnosis" class="diagnosis-card" :style="{ borderLeftColor: stateColor }">
        <div class="diag-header">
          <div class="diag-badge" :style="{ background: stateColor + '22', color: stateColor }">
            {{ diagnosis.state }}
          </div>
          <span class="diag-summary">"{{ diagnosis.summary }}"</span>
          <span class="diag-conf">置信度 {{ Math.round(diagnosis.confidence * 100) }}%</span>
        </div>
        <div class="diag-weights">
          <div v-for="w in weightBars" :key="w.key" class="dw-bar">
            <span class="dw-label" :style="{ color: w.color }">{{ w.label }}</span>
            <div class="dw-track"><div class="dw-fill" :style="{ background: w.color, width: w.pct + '%' }" /></div>
            <span class="dw-pct">{{ w.pct }}%</span>
          </div>
        </div>
      </div>
    </transition>

    <!-- 思考时间线 -->
    <div class="timeline" v-if="thoughts.length > 0">
      <div v-for="(step, i) in thoughts" :key="i" class="tl-node" :class="step.phase">
        <div class="tl-marker" :style="{ background: phaseColor(step.phase) }">
          <span class="tl-icon">{{ phaseIcon(step.phase) }}</span>
        </div>
        <div class="tl-card" @click="toggleThought(i)">
          <div class="tl-header">
            <span class="tl-phase-tag" :style="{ background: phaseColor(step.phase) + '22', color: phaseColor(step.phase) }">
              {{ phaseLabel(step.phase) }}
            </span>
            <span class="tl-title">{{ step.title }}</span>
            <el-icon class="tl-chevron" :class="{ open: expandedThoughts[i] }"><ArrowDown /></el-icon>
          </div>
          <div class="tl-summary">{{ step.summary }}</div>

          <!-- 展开详情 -->
          <transition name="slide">
            <div v-if="expandedThoughts[i]" class="tl-detail">
              <!-- 感知阶段：显示市场数据 -->
              <div v-if="step.phase === 'perceive' && step.data" class="detail-grid">
                <div class="detail-item" v-if="step.data.details?.breadth">
                  <span class="detail-label">涨跌家数</span>
                  <span>{{ step.data.details.breadth.up }}/{{ step.data.details.breadth.down }}</span>
                </div>
                <div class="detail-item" v-if="step.data.details?.breadth?.limit_up">
                  <span class="detail-label">涨停/跌停</span>
                  <span>{{ step.data.details.breadth.limit_up }}/{{ step.data.details.breadth.limit_down }}</span>
                </div>
              </div>

              <!-- 行动阶段：显示工具调用 -->
              <div v-if="step.phase === 'act' && step.data?.counts" class="detail-grid">
                <div class="detail-item" v-for="(v, k) in step.data.counts" :key="k">
                  <span class="detail-label">{{ k }}</span>
                  <span>{{ v }}</span>
                </div>
              </div>

              <!-- 决策阶段：显示评分TOP -->
              <div v-if="step.phase === 'decide' && step.data?.picks" class="detail-picks">
                <span class="detail-label">推荐标的</span>
                <span>{{ step.data.picks.join(', ') }}</span>
              </div>

              <div class="tl-raw" v-if="step.content">
                <span class="raw-label">AI推理:</span>
                <p>{{ step.content }}</p>
              </div>
            </div>
          </transition>
        </div>
      </div>

      <!-- 正在思考中的节点 -->
      <div v-if="running" class="tl-node thinking">
        <div class="tl-marker thinking-marker">
          <el-icon class="spin"><Loading /></el-icon>
        </div>
        <div class="tl-card tl-card-thinking">
          <div class="tl-header">
            <span class="tl-phase-tag" style="background: #8b5cf622; color: #8b5cf6">
              {{ thinkingPhaseLabel }}
            </span>
            <span class="tl-title">AI正在思考...</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="!running && thoughts.length === 0" class="empty-state">
      <el-icon :size="48" style="color: var(--text-muted)"><Cpu /></el-icon>
      <h3>AI 决策中心</h3>
      <p>点击"启动AI决策"按钮，系统将执行完整的感知→判断→行动→决策→复盘流程</p>
      <el-button type="primary" @click="startRun">启动决策</el-button>
    </div>

    <!-- 推荐表格 -->
    <transition name="fade">
      <div v-if="finalPicks.length > 0" class="picks-section">
        <div class="section-header">
          <el-icon style="color: var(--accent-green)"><Trophy /></el-icon>
          <span>今日推荐 ({{ finalPicks.length }}只)</span>
        </div>
        <div class="picks-grid">
          <div v-for="pick in finalPicks" :key="pick.rank" class="pick-card" :style="{ borderLeftColor: scoreColor(pick.score) }">
            <div class="pick-rank">#{{ pick.rank }}</div>
            <div class="pick-main">
              <span class="pick-code">{{ pick.stock_code }}</span>
              <span class="pick-name">{{ pick.stock_name || '--' }}</span>
            </div>
            <div class="pick-score" :style="{ color: scoreColor(pick.score) }">{{ pick.score }}</div>
            <div class="pick-weight">{{ Math.round(pick.weight * 100) }}%</div>
            <div class="pick-signal" :class="pick.signal === '买入' ? 'signal-buy' : 'signal-hold'">{{ pick.signal }}</div>
            <div class="pick-meta" v-if="pick.stop_loss">
              <span class="meta-stop">止 -{{ Math.abs(Math.round(pick.stop_loss * 100)) }}%</span>
              <span class="meta-target">盈 +{{ Math.round(pick.take_profit * 100) }}%</span>
            </div>
            <el-tooltip :content="pick.reason" placement="top">
              <el-icon class="pick-info"><InfoFilled /></el-icon>
            </el-tooltip>
          </div>
        </div>
      </div>
    </transition>

    <!-- 复盘面板 -->
    <transition name="fade">
      <div v-if="reflection" class="reflect-section">
        <div class="section-header" style="color: var(--accent-purple)">
          <el-icon style="color: var(--accent-purple)"><Refresh /></el-icon>
          <span>AI复盘</span>
        </div>
        <div class="reflect-body">
          <p class="reflect-text">{{ reflection.summary }}</p>
          <div v-if="reflection.insights?.length" class="reflect-insights">
            <div v-for="insight in reflection.insights" :key="insight" class="insight-item">
              <el-icon style="color: var(--accent-cyan); margin-right: 4px;"><CaretRight /></el-icon>
              {{ insight }}
            </div>
          </div>
        </div>
      </div>
    </transition>

    <!-- 历史决策 -->
    <div v-if="decisions.length > 0" class="history-section">
      <div class="section-header" style="color: var(--text-muted); font-size: 13px;">
        <el-icon><Clock /></el-icon>
        <span>历史决策</span>
      </div>
      <div class="history-list">
        <div v-for="dec in decisions" :key="dec.date" class="history-item" @click="viewDecision(dec.date)">
          <span class="hist-date">{{ dec.date }}</span>
          <span class="hist-state" :style="{ color: stateColorFromStr(dec.state) }">{{ dec.state }}</span>
          <span class="hist-count">{{ dec.picks_count }}只</span>
          <span class="hist-report">{{ dec.report }}</span>
        </div>
      </div>
    </div>

    <!-- 错误提示 -->
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="true" @close="error = ''" style="margin-top: 12px;" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowDown, Cpu, Loading, Trophy, InfoFilled, Refresh, Clock, CaretRight, CircleClose } from '@element-plus/icons-vue'
import { get } from '@/api/request'

// ── 状态 ──
const running = ref(false)
const diagnosis = ref<any>(null)
const thoughts = ref<any[]>([])
const finalPicks = ref<any[]>([])
const reflection = ref<any>(null)
const decisions = ref<any[]>([])
const error = ref('')
const expandedThoughts = ref<Record<number, boolean>>({})
const thinkingPhase = ref('')

let eventSource: EventSource | null = null

// ── 计算属性 ──

const stateColor = computed(() => {
  const colors: Record<string, string> = { BULL: '#10b981', BEAR: '#ef4444', SHOCK: '#f59e0b', VOLATILE: '#8b5cf6' }
  return colors[diagnosis.value?.state] || '#3b82f6'
})

const weightBars = computed(() => {
  const w = diagnosis.value?.weights || {}
  const labels: Record<string, { label: string; color: string }> = {
    trend: { label: '趋势质量', color: '#3b82f6' },
    capital: { label: '资金行为', color: '#f59e0b' },
    fundamental: { label: 'AI基本面', color: '#10b981' },
    defensive: { label: '防御性', color: '#8b5cf6' },
  }
  return Object.entries(labels).map(([key, meta]) => ({
    key, label: meta.label, color: meta.color, pct: Math.round((w[key] || 0.25) * 100),
  }))
})

const thinkingPhaseLabel = computed(() => {
  const labels: Record<string, string> = { perceive: '感知市场', judge: '策略判断', act: '量化分析', decide: '最终决策', reflect: '复盘' }
  return labels[thinkingPhase.value] || '思考中'
})

const scoreColor = (score: number) => {
  if (score >= 80) return '#10b981'
  if (score >= 60) return '#3b82f6'
  if (score >= 40) return '#f59e0b'
  return '#ef4444'
}

// ── 阶段样式 ──

const phaseColor = (phase: string) => {
  const colors: Record<string, string> = { perceive: '#3b82f6', judge: '#8b5cf6', act: '#f59e0b', decide: '#10b981', reflect: '#ec4899' }
  return colors[phase] || '#6b7280'
}

const phaseLabel = (phase: string) => {
  const labels: Record<string, string> = { perceive: '感知', judge: '判断', act: '行动', decide: '决策', reflect: '复盘' }
  return labels[phase] || phase
}

const phaseIcon = (phase: string) => {
  const icons: Record<string, string> = { perceive: '📡', judge: '🧠', act: '🔧', decide: '✅', reflect: '📝' }
  return icons[phase] || '●'
}

const stateColorFromStr = (state: string) => {
  const colors: Record<string, string> = { BULL: '#10b981', BEAR: '#ef4444', SHOCK: '#f59e0b', VOLATILE: '#8b5cf6' }
  return colors[state] || '#6b7280'
}

// ── 交互 ──

const toggleRun = () => {
  if (running.value) stopRun()
  else startRun()
}

const startRun = () => {
  finalPicks.value = []
  reflection.value = null
  error.value = ''
  expandedThoughts.value = {}
  running.value = true

  // Step 1: 获取市场诊断 (先同步拉取)
  get('/api/quant-agent/state').catch(() => {})
  get('/api/screening/market-state').then((res: any) => {
    if (res?.state) diagnosis.value = res
  }).catch(() => {})

  // Step 2: SSE流式接收思考过程
  const baseUrl = window.location.origin
  const apiUrl = `${baseUrl}/api/quant-agent/daily-cycle/stream`
  eventSource = new EventSource(apiUrl)

  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      handleSSEEvent(data)
    } catch { /* ignore parse errors */ }
  }

  eventSource.onerror = () => {
    // 连接结束（SSE正常完成时也会触发error）
    running.value = false
    if (eventSource) { eventSource.close(); eventSource = null }

    // 如果还没拿到推荐，尝试同步拉取
    if (finalPicks.value.length === 0) {
      get('/api/quant-agent/state').then((res: any) => {
        if (res?.status === 'done' && !error.value) {
          ElMessage.success('决策完成')
        }
      }).catch(() => {})
    }
  }
}

const stopRun = () => {
  if (eventSource) { eventSource.close(); eventSource = null }
  running.value = false
  thinkingPhase.value = ''
}

const handleSSEEvent = (data: any) => {
  const type = data.type

  if (type === 'phase') {
    thinkingPhase.value = data.phase
    return
  }

  if (type === 'thought') {
    thoughts.value.push({
      phase: data.phase,
      title: data.phase === 'perceive' ? '市场感知' : data.phase === 'judge' ? '策略判断' : data.phase === 'act' ? '量化分析' : '决策思考',
      summary: data.content || '',
      content: data.content || '',
      data: data.data || {},
    })
    return
  }

  if (type === 'tool_call') {
    thoughts.value.push({
      phase: 'act',
      title: `调用: ${data.tool}`,
      summary: `参数: ${JSON.stringify(data.params || {})}`,
      content: '',
      data: {},
    })
    return
  }

  if (type === 'tool_result') {
    if (thoughts.value.length > 0) {
      thoughts.value[thoughts.value.length - 1].summary = data.summary || '完成'
    }
    return
  }

  if (type === 'final_recommendation') {
    finalPicks.value = (data.picks || []).map((p: any, i: number) => ({ ...p, rank: i + 1 }))
    thoughts.value.push({
      phase: 'decide',
      title: '最终推荐',
      summary: `推荐${finalPicks.value.length}只标的`,
      content: data.summary || '',
      data: { picks: finalPicks.value.map((p: any) => p.stock_code) },
    })
    running.value = false
    if (eventSource) { eventSource.close(); eventSource = null }
    ElMessage.success(`决策完成: ${finalPicks.value.length}只推荐`)
    return
  }

  if (type === 'reflection') {
    reflection.value = data
    thoughts.value.push({
      phase: 'reflect',
      title: 'AI复盘',
      summary: data.summary || '',
      content: data.summary || '',
      data: { insights: data.insights || [] },
    })
    return
  }

  if (type === 'done') {
    running.value = false
    if (eventSource) { eventSource.close(); eventSource = null }
    return
  }

  if (type === 'error') {
    error.value = data.message || '决策过程出错'
    running.value = false
    if (eventSource) { eventSource.close(); eventSource = null }
  }
}

const toggleThought = (i: number) => {
  expandedThoughts.value[i] = !expandedThoughts.value[i]
}

const viewDecision = (date: string) => {
  get(`/api/quant-agent/decision/${date}`).then((res: any) => {
    if (res?.decision?.picks) {
      finalPicks.value = res.decision.picks
      ElMessage.info(`加载 ${date} 决策`)
    }
  }).catch(() => {
    ElMessage.warning('暂无该日决策记录')
  })
}

// ── 初始化 ──

onMounted(async () => {
  // 加载历史决策列表
  try {
    const res = await get('/api/quant-agent/decisions?limit=10')
    if (res?.decisions) decisions.value = res.decisions
  } catch { /* ignore */ }

  // 尝试加载今日市场诊断
  try {
    const res = await get('/api/screening/market-state')
    if (res?.state) diagnosis.value = res
  } catch { /* ignore */ }
})

onUnmounted(() => {
  if (eventSource) { eventSource.close(); eventSource = null }
})
</script>

<style lang="scss" scoped>
.decision-container {
  max-width: 960px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.header-left { display: flex; align-items: center; gap: 16px; }
.header-meta { display: flex; align-items: center; gap: 8px; }
.meta-text { font-size: 11px; color: var(--text-muted); letter-spacing: 1px; }
.page-title { font-size: 18px; font-weight: 700; }
.title-accent { color: var(--accent-cyan); }
.title-dim { color: var(--text-muted); }

// ── 市场诊断 ──
.diagnosis-card {
  background: rgba(255,255,255,0.02);
  border: 1px solid rgba(255,255,255,0.06);
  border-left-width: 3px;
  border-radius: 8px;
  padding: 14px 18px;
}
.diag-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}
.diag-badge {
  padding: 2px 10px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 1px;
}
.diag-summary { font-size: 13px; color: var(--text-primary); flex: 1; }
.diag-conf { font-size: 11px; color: var(--text-muted); }
.diag-weights { display: flex; gap: 16px; }
.dw-bar { flex: 1; display: flex; align-items: center; gap: 6px; }
.dw-label { font-size: 10px; white-space: nowrap; width: 48px; }
.dw-track { flex: 1; height: 6px; background: rgba(255,255,255,0.06); border-radius: 3px; overflow: hidden; }
.dw-fill { height: 100%; border-radius: 3px; transition: width 0.5s; }
.dw-pct { font-size: 10px; color: var(--text-muted); width: 28px; text-align: right; }

// ── 时间线 ──
.timeline { display: flex; flex-direction: column; gap: 8px; }
.tl-node { display: flex; gap: 12px; position: relative; }
.tl-node::before {
  content: '';
  position: absolute;
  left: 15px;
  top: 32px;
  bottom: -8px;
  width: 2px;
  background: rgba(255,255,255,0.06);
}
.tl-node:last-child::before { display: none; }

.tl-marker {
  width: 32px; height: 32px;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
  z-index: 1;
}
.tl-icon { font-size: 14px; }
.tl-card {
  flex: 1;
  background: rgba(255,255,255,0.02);
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 8px;
  padding: 10px 14px;
  cursor: pointer;
  transition: all 0.2s;
}
.tl-card:hover { background: rgba(255,255,255,0.04); }

.tl-header { display: flex; align-items: center; gap: 8px; }
.tl-phase-tag { padding: 0 8px; border-radius: 3px; font-size: 10px; font-weight: 600; letter-spacing: 0.5px; }
.tl-title { font-size: 13px; font-weight: 500; flex: 1; }
.tl-chevron { transition: transform 0.2s; font-size: 14px; color: var(--text-muted); }
.tl-chevron.open { transform: rotate(180deg); }
.tl-summary { font-size: 11px; color: var(--text-muted); margin-top: 4px; }

.tl-detail { margin-top: 8px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.06); }
.detail-grid { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; }
.detail-item { display: flex; gap: 4px; font-size: 11px; }
.detail-label { color: var(--text-muted); }
.detail-picks { font-size: 11px; margin-bottom: 6px; }
.tl-raw { font-size: 11px; color: var(--text-muted); line-height: 1.5; margin-top: 4px; }
.raw-label { color: var(--text-muted); }
.tl-raw p { margin: 4px 0 0; }

.thinking-marker { background: rgba(139,92,246,0.15); }
.tl-card-thinking { cursor: default; }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

// ── 空状态 ──
.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: var(--text-muted);
}
.empty-state h3 { font-size: 16px; margin: 12px 0 8px; }
.empty-state p { font-size: 12px; margin: 0 0 16px; max-width: 400px; margin-inline: auto; }

// ── 推荐表格 ──
.picks-section { }
.section-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 10px;
}
.picks-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 8px;
}
.pick-card {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: rgba(255,255,255,0.02);
  border: 1px solid rgba(255,255,255,0.06);
  border-left-width: 3px;
  border-radius: 6px;
  font-size: 12px;
  position: relative;
}
.pick-rank { font-size: 10px; color: var(--text-muted); width: 16px; }
.pick-main { display: flex; flex-direction: column; min-width: 0; flex: 1; }
.pick-code { font-weight: 600; font-family: 'JetBrains Mono', monospace; }
.pick-name { font-size: 10px; color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pick-score { font-size: 16px; font-weight: 700; font-family: 'JetBrains Mono', monospace; width: 32px; text-align: center; }
.pick-weight { font-size: 12px; color: var(--text-muted); width: 40px; text-align: center; }
.pick-signal { font-size: 10px; padding: 1px 6px; border-radius: 3px; }
.signal-buy { background: rgba(16,185,129,0.15); color: #10b981; }
.signal-hold { background: rgba(59,130,246,0.15); color: #3b82f6; }
.pick-meta { font-size: 10px; color: var(--text-muted); display: flex; flex-direction: column; align-items: flex-end; }
.pick-info { font-size: 12px; color: var(--text-muted); cursor: help; }

// ── 复盘 ──
.reflect-section { }
.reflect-body {
  background: rgba(139,92,246,0.04);
  border: 1px solid rgba(139,92,246,0.1);
  border-radius: 8px;
  padding: 12px 16px;
}
.reflect-text { font-size: 12px; line-height: 1.6; margin: 0; color: var(--text-primary); }
.reflect-insights { margin-top: 8px; display: flex; flex-direction: column; gap: 4px; }
.insight-item { font-size: 11px; color: var(--accent-cyan); display: flex; align-items: center; }

// ── 历史 ──
.history-section { }
.history-list { display: flex; flex-direction: column; gap: 2px; }
.history-item {
  display: flex; align-items: center; gap: 12px;
  padding: 6px 10px;
  font-size: 11px;
  cursor: pointer;
  border-radius: 4px;
  transition: background 0.15s;
}
.history-item:hover { background: rgba(255,255,255,0.04); }
.hist-date { color: var(--text-muted); font-family: 'JetBrains Mono', monospace; width: 80px; }
.hist-state { font-weight: 600; width: 60px; }
.hist-count { color: var(--text-muted); width: 40px; }
.hist-report { color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }

// ── 过渡动画 ──
.fade-enter-active, .fade-leave-active { transition: opacity 0.3s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
.slide-enter-active, .slide-leave-active { transition: all 0.2s; }
.slide-enter-from, .slide-leave-to { opacity: 0; max-height: 0; overflow: hidden; }
</style>
