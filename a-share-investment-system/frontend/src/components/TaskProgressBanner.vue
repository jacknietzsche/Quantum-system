<template>
  <div v-if="visible" class="task-progress-banner card p-3 mb-4">
    <div class="flex items-center justify-between mb-2">
      <div class="flex items-center gap-2">
        <el-icon class="is-loading" style="color: var(--accent-blue)"><Loading /></el-icon>
        <span class="mono text-sm font-semibold" style="color: var(--text-primary)">{{ title || '任务进行中' }}</span>
      </div>
      <el-tag size="small" effect="dark" type="warning">{{ status }}</el-tag>
    </div>
    <el-progress :percentage="progress" :stroke-width="6" color="var(--accent-blue)" :show-text="false" />
    <div class="flex justify-between mt-1">
      <span class="mono text-xs" style="color: var(--text-muted)">{{ currentStage }}</span>
      <span class="mono text-xs" style="color: var(--text-muted)">{{ progress }}%</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Loading } from '@element-plus/icons-vue'

defineProps<{
  visible?: boolean
  title?: string
  status?: string
  progress?: number
  currentStage?: string
}>()
</script>
