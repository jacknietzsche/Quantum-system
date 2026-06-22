<template>
  <el-dialog
    :model-value="true"
    :title="stockCode"
    width="680px"
    close-on-click-modal
    @close="$emit('close')"
  >
    <template #header>
      <div>
        <h2 class="text-xl font-bold">{{ stockCode }}</h2>
        <span
          v-if="data?.signal"
          class="text-sm"
          :class="signalColorClass(data.signal)"
        >
          {{ signalLabel(data.signal) }}
        </span>
      </div>
    </template>

    <el-tabs v-model="tab">
      <el-tab-pane label="估值" name="valuation" />
      <el-tab-pane label="因子" name="factors" />
    </el-tabs>

    <div class="content-area" style="max-height: 60vh; overflow: auto">
      <div v-if="tab === 'valuation' && data?.valuation" class="space-y-3">
        <div
          v-for="(v, name) in data.valuation"
          :key="name"
          class="card p-4"
        >
          <div class="flex justify-between items-center mb-2">
            <span class="font-medium text-lg capitalize">{{ name }}</span>
            <span
              class="px-2 py-1 rounded text-sm font-medium"
              :class="signalBgClass(v.signal)"
            >
              {{ v.signal }} · {{ v.score }}分
            </span>
          </div>
          <div v-if="v.details" class="grid grid-cols-2 gap-2 text-sm">
            <div
              v-for="item in visibleDetails(v.details, 6)"
              :key="item.key"
              class="px-3 py-1.5 rounded"
              style="background: var(--bg-root)"
            >
              <span style="color: var(--text-muted)">{{ item.key }}: </span>
              <span>{{ formatValue(item.value) }}</span>
            </div>
          </div>
        </div>
      </div>

      <div v-if="tab === 'factors' && data?.factors?.factors" class="space-y-2">
        <div
          v-for="(f, i) in data.factors.factors"
          :key="i"
          class="flex justify-between items-center py-3 px-4 card"
        >
          <div>
            <span class="font-medium">{{ f.name }}</span>
            <span
              class="ml-2 text-xs px-2 py-0.5 rounded"
              style="background: var(--bg-root); color: var(--text-muted)"
            >
              {{ f.category }}
            </span>
          </div>
          <div class="text-right">
            <span :class="f.ic_mean >= 0 ? 'num-up' : 'num-down'">
              IC: {{ (f.ic_mean || 0).toFixed(3) }}
            </span>
            <span class="ml-3" style="color: var(--text-muted)">
              IR: {{ (f.icir || 0).toFixed(2) }}
            </span>
          </div>
        </div>
      </div>

      <div v-if="loading" class="text-center py-10" style="color: var(--text-muted)">
        加载中...
      </div>

      <div v-if="loadError" class="text-center py-10" style="color: var(--accent-red)">
        <p>加载失败: {{ loadError }}</p>
        <el-button class="mt-3" size="small" @click="loadData">重试</el-button>
      </div>

      <div v-if="data?.error" class="text-center py-10" style="color: var(--accent-red)">
        分析失败: {{ data.error }}
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { get } from '@/api/request'

const props = defineProps<{
  stockCode: string
}>()

defineEmits<{
  close: []
}>()

const data = ref<any>(null)
const tab = ref('valuation')
const loading = ref(true)
const loadError = ref<string | null>(null)

const signalColorClass = (signal: string) => {
  if (signal === 'bullish') return 'text-green-400'
  if (signal === 'bearish') return 'text-red-400'
  return 'text-yellow-400'
}

const signalLabel = (signal: string) => {
  if (signal === 'bullish') return '看多'
  if (signal === 'bearish') return '看空'
  return '中性'
}

const signalBgClass = (signal: string) => {
  if (signal === 'bullish') return 'bg-green-900/50 text-green-400'
  if (signal === 'bearish') return 'bg-red-900/50 text-red-400'
  return 'bg-yellow-900/50 text-yellow-400'
}

const visibleDetails = (details: Record<string, unknown>, limit: number) => {
  return Object.entries(details).slice(0, limit).map(([key, value]) => ({ key, value }))
}

const formatValue = (val: unknown): string => {
  if (typeof val === 'number') return val.toFixed(2)
  if (val === null || val === undefined) return '--'
  return String(val)
}

const loadData = async () => {
  loading.value = true
  loadError.value = null
  try {
    data.value = await get(`/api/analysis/${props.stockCode}`)
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : '请求失败'
  } finally {
    loading.value = false
  }
}

loadData()
</script>

<style lang="scss" scoped>
.content-area {
  .card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
  }
}
</style>
