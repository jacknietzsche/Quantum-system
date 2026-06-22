<template>
  <div class="risk-items">
    <div class="mono text-xs tracking-wider uppercase mb-3" style="color: var(--text-muted)">风险评估</div>
    <div v-if="!items?.length" class="text-center py-4 mono text-xs" style="color: var(--text-muted)">暂无风险项</div>
    <div v-for="(item, i) in items" :key="i" class="risk-item" :class="item.severity">
      <el-icon :size="14" :style="{ color: severityColor(item.severity) }">
        <WarningFilled v-if="item.severity === 'high'" />
        <Warning v-else-if="item.severity === 'medium'" />
        <InfoFilled v-else />
      </el-icon>
      <div class="flex-1 ml-2">
        <div class="text-sm">{{ item.title }}</div>
        <div v-if="item.description" class="mono text-xs mt-0.5" style="color: var(--text-muted)">{{ item.description }}</div>
      </div>
      <el-tag :type="tagType(item.severity)" size="small" effect="plain">{{ item.severity }}</el-tag>
    </div>
  </div>
</template>

<script setup lang="ts">
import { WarningFilled, Warning, InfoFilled } from '@element-plus/icons-vue'

defineProps<{
  items?: Array<{ title: string; description?: string; severity: 'high' | 'medium' | 'low' }>
}>()

const severityColor = (s: string) => s === 'high' ? '#e33545' : s === 'medium' ? '#d49a00' : '#2b6de5'
const tagType = (s: string) => s === 'high' ? 'danger' : s === 'medium' ? 'warning' : 'info'
</script>

<style lang="scss" scoped>
.risk-item {
  display: flex;
  align-items: flex-start;
  padding: 10px 12px;
  border-radius: 6px;
  margin-bottom: 6px;
  background: var(--bg-root);
  border: 1px solid var(--border);

  &.high { border-left: 3px solid #e33545; }
  &.medium { border-left: 3px solid #d49a00; }
  &.low { border-left: 3px solid #2b6de5; }
}
</style>
