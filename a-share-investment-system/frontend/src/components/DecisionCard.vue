<template>
  <div class="decision-card">
    <div class="flex items-center justify-between mb-3">
      <span class="mono text-xs tracking-wider uppercase" style="color: var(--text-muted)">决策建议</span>
      <el-tag v-if="decision" :type="tagType" size="small" effect="dark">
        {{ decisionText }}
      </el-tag>
    </div>
    <div v-if="confidence !== undefined" class="mb-3">
      <div class="flex justify-between mono text-xs mb-1" style="color: var(--text-secondary)">
        <span>置信度</span><span>{{ confidence }}%</span>
      </div>
      <el-progress :percentage="confidence" :color="confidenceColor" :stroke-width="6" />
    </div>
    <div v-if="targetPrice" class="grid grid-cols-2 gap-2 mb-2">
      <div class="card p-2 text-center">
        <div class="mono text-xs" style="color: var(--text-muted)">目标价</div>
        <div class="text-lg font-bold mono num-up">{{ targetPrice }}</div>
      </div>
      <div class="card p-2 text-center">
        <div class="mono text-xs" style="color: var(--text-muted)">止损价</div>
        <div class="text-lg font-bold mono num-down">{{ stopLoss }}</div>
      </div>
    </div>
    <div v-if="reasoning" class="mt-2">
      <el-collapse>
        <el-collapse-item title="推理详情" name="reasoning">
          <div class="mono text-xs" style="color: var(--text-secondary); white-space: pre-wrap">{{ reasoning }}</div>
        </el-collapse-item>
      </el-collapse>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  decision?: string
  confidence?: number
  targetPrice?: string | number
  stopLoss?: string | number
  reasoning?: string
}>()

const tagType = computed(() => {
  if (props.decision === 'buy' || props.decision === 'bullish') return 'success'
  if (props.decision === 'sell' || props.decision === 'bearish') return 'danger'
  return 'warning'
})

const decisionText = computed(() => {
  if (props.decision === 'buy' || props.decision === 'bullish') return '买入'
  if (props.decision === 'sell' || props.decision === 'bearish') return '卖出'
  return '持有'
})

const confidenceColor = computed(() => {
  const c = props.confidence || 0
  if (c >= 70) return '#00a85a'
  if (c >= 40) return '#d49a00'
  return '#e33545'
})
</script>
