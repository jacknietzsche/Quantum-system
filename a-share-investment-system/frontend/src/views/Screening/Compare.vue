<template>
  <div class="compare-container">
    <div class="space-y-4 max-w-5xl">
      <div class="flex justify-between items-center">
        <h1 class="text-lg font-semibold tracking-wide mono" style="color: var(--text-primary)">
          COMPARE STYLES
        </h1>
        <el-button :loading="loading" @click="loadComparison" type="primary">
          {{ loading ? 'ANALYZING...' : 'RUN COMPARISON' }}
        </el-button>
      </div>

      <div v-if="loading" class="card p-4">
        <div class="mono text-xs mb-2" style="color: var(--text-secondary)">
          Running all 4 styles in parallel...
        </div>
        <div class="progress-bar">
          <div class="progress-fill" :style="{ width: `${progress}%` }" />
        </div>
      </div>

      <div v-if="!loading && results.length > 0" class="grid grid-cols-4 gap-3 mb-6">
        <div
          v-for="(v, i) in results" :key="v.style"
          class="card p-3 text-center"
          :style="{ borderLeft: `3px solid ${styleColors[v.style]}` }"
        >
          <div class="text-xs uppercase mono mb-2" style="color: var(--text-muted)">
            {{ styleLabels[v.style] }}
          </div>
          <div class="text-2xl font-bold mono" :style="{ color: styleColors[v.style] }">
            {{ v.total_screened || 0 }} → {{ v.stage3_recommended || 0 }}
          </div>
          <div class="text-xs mono mt-1" style="color: var(--text-muted)">
            Stage1: {{ v.stage1_passed }} / Stage2: {{ v.stage2_passed }}
          </div>
        </div>
      </div>

      <div v-if="!loading && combined.length > 0">
        <div class="flex items-center gap-2 mb-3">
          <span class="text-sm font-medium" style="color: var(--text-primary)">Cross-Style Comparison</span>
          <span class="text-xs" style="color: var(--text-muted)">{{ combined.length }} stocks found by multiple styles</span>
        </div>
        <div class="card p-0 overflow-hidden">
          <el-table :data="combined" size="small" stripe style="width: 100%">
            <el-table-column label="Code" width="90">
              <template #default="{ row }">
                <span class="mono text-sm" style="color: var(--accent-blue)">{{ row.code }}</span>
              </template>
            </el-table-column>
            <el-table-column label="Name" prop="name" width="90" show-overflow-tooltip />
            <el-table-column label="Industry" prop="industry" width="110" show-overflow-tooltip />
            <el-table-column label="Cross" width="80" align="center">
              <template #default="{ row }">
                <span v-if="row.styles.length >= 3" class="badge badge-up text-xs">✓ 交叉</span>
                <span v-else class="text-xs" style="color: var(--text-muted)">{{ row.styles.length }}x</span>
              </template>
            </el-table-column>
            <el-table-column v-for="s in STYLES" :key="s" :label="styleLabels[s]" :min-width="110">
              <template #default="{ row }">
                <div v-if="getStyleData(row, s)" class="flex items-center gap-1">
                  <span class="mono text-xs font-semibold" :style="{ color: getColor(s, getStyleData(row, s)) }">
                    {{ getStyleData(row, s).score }}
                  </span>
                  <span class="badge text-xs" :class="signalClass(getStyleData(row, s).signal)">
                    {{ getStyleData(row, s).signal }}
                  </span>
                </div>
                <span v-else class="text-xs" style="color: var(--text-muted)">—</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>

      <div
        v-if="!loading && results.length === 0"
        class="text-center py-20 mono text-sm"
        style="color: var(--text-muted)"
      >
        Press RUN COMPARISON to start multi-style analysis
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { get } from '@/api/request'

const STYLES = ['limit_up', 'momentum', 'value', 'hybrid'] as const

const styleColors: Record<string, string> = {
  limit_up: '#ef4444',
  momentum: '#f59e0b',
  value: '#10b981',
  hybrid: '#3b82f6',
}

const styleLabels: Record<string, string> = {
  limit_up: '涨停狙击',
  momentum: '中期趋势',
  value: '长期价值',
  hybrid: '混合均衡',
}

const loading = ref(false)
const progress = ref(0)
const saved = sessionStorage.getItem('screening_compare')
const results = ref<any[]>(saved ? JSON.parse(saved) : [])
const combined = ref<any[]>([])
watch(results, (v) => sessionStorage.setItem('screening_compare', JSON.stringify(v)), { deep: true })

const delay = (ms: number) => new Promise(r => setTimeout(r, ms))

const loadComparison = async () => {
  loading.value = true
  progress.value = 0
  results.value = []
  combined.value = []

  const allResults: any[] = []
  const allRecs: Record<string, any> = {}

  // Run all 4 styles in parallel
  const promises = STYLES.map(async (style, i) => {
    progress.value = ((i + 1) / STYLES.length) * 25

    try {
      await get(`/api/screening/run?style=${style}`)
      // Poll /status until done, up to 120s
      for (let attempt = 0; attempt < 60; attempt++) {
        await delay(2000)
        const st: any = await get('/api/screening/status')
        if (!st.running || st.results) break
      }
      const r = await get('/api/screening/results')
      const data = r as any
      data.style = style
      return data
    } catch {
      return { style, total_screened: 0, stage1_passed: 0, stage2_passed: 0, stage3_recommended: 0, recommendations: [] }
    }
  })

  const settled = await Promise.allSettled(promises)

  for (const result of settled) {
    if (result.status === 'fulfilled') {
      const data = result.value
      allResults.push(data)

      if (data.recommendations) {
        for (const rec of data.recommendations) {
          if (!allRecs[rec.stock_code]) {
            allRecs[rec.stock_code] = {
              code: rec.stock_code, name: rec.stock_name,
              industry: rec.industry, styles: [],
            }
          }
          allRecs[rec.stock_code].styles.push({
            style: data.style, score: rec.score, signal: rec.signal,
          })
        }
      }
    }
  }

  results.value = allResults
  combined.value = Object.values(allRecs).sort(
    (a: any, b: any) => b.styles.length - a.styles.length
  )
  progress.value = 100
  loading.value = false
}

const getStyleData = (stock: any, style: string) => {
  return stock.styles?.find((s: any) => s.style === style) || null
}

const getColor = (style: string, data: any) => {
  return styleColors[style]
}

const signalClass = (signal: string) => {
  if (signal === '买入' || signal === 'bullish') return 'badge-up'
  if (signal === '卖出' || signal === 'bearish') return 'badge-down'
  return 'badge-warn'
}
</script>

<style lang="scss" scoped>
.compare-container {
  .mono {
    font-family: 'JetBrains Mono', monospace;
  }
}
</style>
