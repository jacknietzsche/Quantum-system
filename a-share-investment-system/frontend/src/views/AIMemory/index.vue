<template>
  <div class="aimemory-container">
    <div class="max-w-5xl mx-auto space-y-4">
      <!-- 顶部栏 -->
      <div class="page-header">
        <div class="header-left">
          <h1 class="page-title">
            <span class="title-accent">AI</span><span class="title-dim"> 复盘</span>
          </h1>
          <div class="header-meta">
            <span class="meta-text">AI MEMORY</span>
            <span class="meta-divider" />
            <span class="meta-text">自我进化</span>
          </div>
        </div>
        <div class="header-right">
          <el-date-picker
            v-model="selectedMonth"
            type="month"
            placeholder="选择月份"
            format="YYYY-MM"
            value-format="YYYY-MM"
            size="small"
            style="width: 140px"
            @change="loadCalendar"
          />
        </div>
      </div>

      <!-- 加载状态 -->
      <div v-if="loading" class="text-center py-20">
        <el-icon class="is-loading" :size="24" style="color: var(--accent-blue)"><Loading /></el-icon>
        <div class="mono text-xs mt-2" style="color: var(--text-muted)">加载复盘数据...</div>
      </div>

      <template v-else>
        <!-- 复盘日历 -->
        <div class="card calendar-card">
          <div class="cal-header">
            <el-icon :size="14" style="color: var(--accent-cyan)"><Calendar /></el-icon>
            <span>复盘日历</span>
            <div class="cal-legend">
              <span class="legend-item"><span class="legend-dot" style="background: var(--accent-green)" /> &gt;+2%</span>
              <span class="legend-item"><span class="legend-dot" style="background: var(--accent-amber)" /> &gt;0%</span>
              <span class="legend-item"><span class="legend-dot" style="background: var(--accent-red)" /> &lt;0%</span>
            </div>
          </div>
          <div class="cal-body">
            <div class="cal-weekdays">
              <span v-for="d in weekdays" :key="d" class="cal-wd">{{ d }}</span>
            </div>
            <div class="cal-grid">
              <div
                v-for="(cell, i) in calendarCells"
                :key="i"
                class="cal-cell"
                :class="{ 'has-data': cell.day, 'selected': selectedDate === cell.date }"
                :style="cellStyle(cell)"
                @click="selectDay(cell)"
              >
                <span class="cal-day">{{ cell.day || '' }}</span>
                <span v-if="cell.dayData" class="cal-return">{{ cell.dayData.avg_return > 0 ? '+' : '' }}{{ (cell.dayData.avg_return * 100).toFixed(1) }}%</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 当日复盘详情 -->
        <div v-if="selectedDayData" class="card review-card">
          <div class="review-header">
            <el-icon :size="14" style="color: var(--accent-blue)"><Document /></el-icon>
            <span>{{ selectedDayData.trade_date }}</span>
            <el-tag size="small" :type="regimeTag(selectedDayData.regime)">{{ selectedDayData.regime }}</el-tag>
            <div class="review-stats">
              <span class="rs-item">
                命中 <strong :style="{ color: selectedDayData.avg_return >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }">
                  {{ selectedDayData.correct_count }}/{{ selectedDayData.picks_count }}
                </strong>
              </span>
              <span class="rs-sep" />
              <span class="rs-item">
                收益 <strong :style="{ color: selectedDayData.avg_return >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }">
                  {{ (selectedDayData.avg_return * 100).toFixed(1) }}%
                </strong>
              </span>
              <span class="rs-sep" />
              <span class="rs-item">
                大盘 <strong :style="{ color: (selectedDayData.market_return || 0) >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }">
                  {{ (selectedDayData.market_return * 100).toFixed(1) }}%
                </strong>
              </span>
            </div>
          </div>
          <div v-if="selectedDayData.reflection" class="review-reflection">
            <div class="rr-label">AI反思:</div>
            <div class="rr-text">{{ selectedDayData.reflection }}</div>
          </div>
        </div>

        <!-- 相似市场检索 -->
        <div v-if="similarMarkets.length > 0" class="card similar-card">
          <div class="similar-header">
            <el-icon :size="14" style="color: var(--accent-purple)"><Search /></el-icon>
            <span>相似市场历史</span>
            <span class="similar-hint">基于 {{ selectedDate || selectedMonth || '当前' }} 市场状态</span>
          </div>
          <div class="similar-list">
            <div v-for="(s, i) in similarMarkets" :key="i" class="similar-item">
              <div class="si-left">
                <span class="si-date">{{ s.trade_date }}</span>
                <span class="si-sim">相似度 {{ (s.similarity * 100).toFixed(0) }}%</span>
              </div>
              <div class="si-mid">
                <span class="si-tag" :style="siTagStyle(s.regime)">{{ s.regime }}</span>
                <span class="si-strategy">策略: {{ s.strategy }}</span>
              </div>
              <div class="si-right">
                <span class="si-result" :class="s.result >= 0 ? 'num-up' : 'num-down'">
                  {{ s.result >= 0 ? '+' : '' }}{{ (s.result * 100).toFixed(1) }}%
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- 空状态 -->
        <div v-if="!calendarDays?.length && !loading" class="text-center py-20 mono text-sm" style="color: var(--text-muted)">
          暂无复盘数据 — AI系统正在积累交易记忆
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { aiApi } from '@/api/ai'
import { Calendar, Document, Search, Loading } from '@element-plus/icons-vue'

const weekdays = ['日', '一', '二', '三', '四', '五', '六']

// ── State ──
const loading = ref(true)
const calendarDays = ref<any[]>([])
const selectedDate = ref<string | null>(null)
const selectedMonth = ref<string | null>(null)
const similarMarkets = ref<any[]>([])

// Computed
const selectedDayData = computed(() => {
  if (!selectedDate.value) return null
  return calendarDays.value.find(d => d.trade_date === selectedDate.value) || null
})

// ── Calendar cell generation ──
function getDaysInMonth(year: number, month: number): number {
  return new Date(year, month + 1, 0).getDate()
}

function getFirstDayOfMonth(year: number, month: number): number {
  return new Date(year, month, 1).getDay()
}

const calendarCells = computed(() => {
  if (!calendarDays.value?.length) return []

  // Determine month from data or default to current
  const now = selectedMonth.value ? new Date(selectedMonth.value + '-01') : new Date()
  const year = now.getFullYear()
  const month = now.getMonth()
  const daysInMonth = getDaysInMonth(year, month)
  const firstDay = getFirstDayOfMonth(year, month)

  const cells: any[] = []
  // Empty cells before first day
  for (let i = 0; i < firstDay; i++) {
    cells.push({ day: null, date: null, dayData: null })
  }
  // Day cells
  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`
    const dayData = calendarDays.value.find((cd: any) => cd.trade_date === dateStr) || null
    cells.push({ day: d, date: dateStr, dayData })
  }
  return cells
})

function cellStyle(cell: any) {
  if (!cell.dayData) return {}
  const r = cell.dayData.avg_return
  if (r >= 0.02) return { background: 'rgba(16, 185, 129, 0.12)', borderColor: 'rgba(16, 185, 129, 0.25)' }
  if (r >= 0) return { background: 'rgba(245, 158, 11, 0.10)', borderColor: 'rgba(245, 158, 11, 0.20)' }
  return { background: 'rgba(239, 68, 68, 0.10)', borderColor: 'rgba(239, 68, 68, 0.20)' }
}

function regimeTag(regime: string): string {
  if (regime === 'BULL' || regime === 'EUPHORIA') return 'success'
  if (regime === 'BEAR' || regime === 'PANIC') return 'danger'
  if (regime === 'DIVERGENCE') return 'warning'
  return 'info'
}

function siTagStyle(regime: string) {
  if (regime === 'BULL' || regime === 'EUPHORIA') return { background: 'rgba(16,185,129,0.08)', color: 'var(--accent-green)' }
  if (regime === 'BEAR' || regime === 'PANIC') return { background: 'rgba(239,68,68,0.08)', color: 'var(--accent-red)' }
  if (regime === 'DIVERGENCE') return { background: 'rgba(139,92,246,0.08)', color: 'var(--accent-purple)' }
  return { background: 'rgba(59,130,246,0.08)', color: 'var(--accent-blue)' }
}

// ── Actions ──
function selectDay(cell: any) {
  if (!cell.day || !cell.dayData) return
  selectedDate.value = cell.date
  loadSimilarMarkets(cell.date)
}

async function loadCalendar() {
  loading.value = true
  try {
    const data = await aiApi.getMemoryCalendar(30)
    calendarDays.value = data.days || []
    // Auto-select most recent day
    if (calendarDays.value.length > 0 && !selectedDate.value) {
      selectedDate.value = calendarDays.value[0].trade_date
      loadSimilarMarkets(selectedDate.value)
    }
  } catch (e) {
    console.error('Failed to load calendar:', e)
    calendarDays.value = []
  } finally {
    loading.value = false
  }
}

async function loadSimilarMarkets(date: string) {
  try {
    const data = await aiApi.getSimilarMarkets(date)
    similarMarkets.value = data.similar_days || []
  } catch {
    similarMarkets.value = []
  }
}

onMounted(() => {
  // Set current month
  const now = new Date()
  selectedMonth.value = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  loadCalendar()
})
</script>

<style lang="scss" scoped>
.aimemory-container {
  .mono { font-family: 'JetBrains Mono', monospace; }
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

// ── 复盘日历 ──
.calendar-card {
  padding: 20px;
}

.cal-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
  font-family: 'JetBrains Mono', monospace;
  margin-bottom: 16px;
}

.cal-legend {
  margin-left: auto;
  display: flex;
  gap: 12px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  color: var(--text-muted);
}

.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.cal-weekdays {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 4px;
  margin-bottom: 8px;
}

.cal-wd {
  text-align: center;
  font-size: 10px;
  font-family: 'JetBrains Mono', monospace;
  color: var(--text-muted);
  padding: 4px 0;
}

.cal-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 4px;
}

.cal-cell {
  aspect-ratio: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  border: 1px solid transparent;
  cursor: pointer;
  transition: all 0.2s;
  min-height: 48px;

  &.has-data:hover {
    border-color: var(--border-glow);
  }

  &.selected {
    border-color: var(--accent-blue) !important;
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.15);
  }
}

.cal-day {
  font-size: 11px;
  font-family: 'JetBrains Mono', monospace;
  font-weight: 600;
  color: var(--text-primary);
}

.cal-return {
  font-size: 9px;
  font-family: 'JetBrains Mono', monospace;
  font-weight: 500;
  color: var(--text-secondary);
}

// ── 复盘详情 ──
.review-card {
  padding: 20px;
}

.review-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
  font-family: 'JetBrains Mono', monospace;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.review-stats {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
}

.rs-item {
  font-size: 11px;
  color: var(--text-secondary);

  strong { font-weight: 600; }
}

.rs-sep {
  width: 1px;
  height: 10px;
  background: var(--border);
}

.review-reflection {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 14px;
}

.rr-label {
  font-size: 10px;
  font-weight: 600;
  font-family: 'JetBrains Mono', monospace;
  color: var(--accent-cyan);
  margin-bottom: 4px;
}

.rr-text {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
}

// ── 相似市场 ──
.similar-card {
  padding: 20px;
}

.similar-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
  font-family: 'JetBrains Mono', monospace;
  margin-bottom: 12px;
}

.similar-hint {
  margin-left: auto;
  font-size: 9px;
  color: var(--text-muted);
  font-weight: 400;
}

.similar-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.similar-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 8px;
}

.si-left {
  display: flex;
  flex-direction: column;
  min-width: 80px;
}

.si-date {
  font-size: 13px;
  font-weight: 600;
  font-family: 'JetBrains Mono', monospace;
  color: var(--text-primary);
}

.si-sim {
  font-size: 10px;
  color: var(--text-muted);
  font-family: 'JetBrains Mono', monospace;
}

.si-mid {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
}

.si-tag {
  font-size: 10px;
  font-family: 'JetBrains Mono', monospace;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
}

.si-strategy {
  font-size: 11px;
  color: var(--text-secondary);
}

.si-right {
  text-align: right;
}

.si-result {
  font-size: 15px;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
}
</style>
