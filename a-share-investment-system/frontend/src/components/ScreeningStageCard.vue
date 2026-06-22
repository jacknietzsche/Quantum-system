<template>
  <div class="stage-card" :class="[`stage-${status}`, { clickable: true }]" @click="emit('click')">
    <div class="stage-header">
      <span class="stage-icon">{{ iconMap[status] }}</span>
      <span class="stage-name">{{ name }}</span>
    </div>
    <div class="stage-body">
      <div class="stage-status">{{ statusText }}</div>
      <div v-if="metrics" class="stage-metrics mono text-xs">
        <div v-for="(v, k) in metrics" :key="k" class="metric-row">
          <span class="metric-key">{{ k }}:</span>
          <span class="metric-val">{{ v }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  name: string
  status: 'waiting' | 'running' | 'done' | 'failed'
  metrics?: Record<string, string | number> | null
}>()

const emit = defineEmits<{
  (e: 'click'): void
}>()

const iconMap: Record<string, string> = {
  waiting: '○',
  running: '⟳',
  done: '✓',
  failed: '✗',
}

const statusText = computed(() => {
  const map: Record<string, string> = {
    waiting: '等待',
    running: '进行中',
    done: '完成',
    failed: '失败',
  }
  return map[props.status]
})
</script>

<style scoped>
.stage-card {
  flex: 1;
  min-width: 140px;
  padding: 12px;
  border-radius: 8px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  background: rgba(0, 0, 0, 0.02);
  transition: all 0.3s ease;
}
.stage-card.clickable { cursor: pointer; }
.stage-card.clickable:hover {
  border-color: var(--accent-blue, #3b82f6);
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.12);
}

.stage-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}
.stage-icon {
  font-size: 16px;
  width: 20px;
  text-align: center;
}
.stage-name {
  font-size: 12px;
  font-weight: 600;
  font-family: 'JetBrains Mono', monospace;
}

.stage-status {
  font-size: 11px;
  margin-bottom: 6px;
}

.stage-metrics {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.metric-row {
  display: flex;
  justify-content: space-between;
  gap: 4px;
}
.metric-key {
  color: var(--text-muted);
}
.metric-val {
  color: var(--text-secondary);
  font-weight: 500;
}

/* Status colors */
.stage-waiting {
  border-color: rgba(156, 163, 175, 0.3);
  color: #9ca3af;
}

.stage-running {
  border-color: #3b82f6;
  background: rgba(59, 130, 246, 0.04);
  color: #3b82f6;
}
.stage-running .stage-icon {
  animation: pulse 1.2s ease-in-out infinite;
}

.stage-done {
  border-color: #10b981;
  background: rgba(16, 185, 129, 0.04);
  color: #10b981;
}

.stage-failed {
  border-color: #ef4444;
  background: rgba(239, 68, 68, 0.04);
  color: #ef4444;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

@keyframes glow-pulse {
  0%, 100% {
    box-shadow: 0 0 4px rgba(59, 130, 246, 0.3);
    border-color: rgba(59, 130, 246, 0.5);
  }
  50% {
    box-shadow: 0 0 12px rgba(59, 130, 246, 0.5);
    border-color: rgba(59, 130, 246, 0.8);
  }
}
.stage-running {
  animation: glow-pulse 1.5s ease-in-out infinite;
}
.glow-pulse {
  animation: glow-pulse 2s ease-in-out infinite;
}
</style>
