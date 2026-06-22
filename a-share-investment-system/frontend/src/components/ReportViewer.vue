<template>
  <div class="report-viewer">
    <div v-if="!sections?.length" class="text-center py-10 mono text-sm" style="color: var(--text-muted)">暂无报告内容</div>
    <el-collapse v-model="activeNames" v-for="(section, i) in sections" :key="i">
      <el-collapse-item :title="section.title" :name="i">
        <div v-if="section.streaming" class="streaming-text mono text-sm" style="color: var(--text-secondary)">
          {{ section.content }}<span class="cursor-blink">|</span>
        </div>
        <div v-else class="markdown-body mono text-sm" style="color: var(--text-secondary); white-space: pre-wrap">{{ section.content }}</div>
        <div v-if="section.verdict" class="mt-2">
          <el-tag :type="verdictType(section.verdict)" size="small" effect="dark">
            {{ section.verdict }}
          </el-tag>
        </div>
      </el-collapse-item>
    </el-collapse>
    <div v-if="onExport" class="mt-4 text-right">
      <el-button text size="small" @click="handleExport">
        <el-icon><Download /></el-icon> 导出报告
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Download } from '@element-plus/icons-vue'

const props = defineProps<{
  sections?: Array<{ title: string; content: string; streaming?: boolean; verdict?: string }>
  onExport?: () => void
}>()

const activeNames = ref([0])

const verdictType = (v: string) => v === 'bullish' ? 'success' : v === 'bearish' ? 'danger' : 'warning'

const handleExport = () => props.onExport?.()
</script>

<style lang="scss" scoped>
.cursor-blink {
  animation: blink 1s step-end infinite;
}
@keyframes blink {
  50% { opacity: 0; }
}
</style>
