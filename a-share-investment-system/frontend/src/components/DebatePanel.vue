<template>
  <el-drawer v-model="visible" :title="mode === 'research' ? '多空辩论' : '风控三方辩论'" size="50%" @close="$emit('close')">
    <div v-if="!rounds?.length" class="text-center py-10 mono text-sm" style="color: var(--text-muted)">暂无辩论内容</div>
    <div v-for="(round, ri) in rounds" :key="ri" class="mb-4">
      <el-tag size="small" effect="dark" class="mb-2">第 {{ ri + 1 }} 轮</el-tag>
      <div v-for="(msg, mi) in round.messages" :key="mi" class="debate-msg mb-2" :class="msg.role">
        <div class="flex items-center gap-2 mb-1">
          <span class="font-bold text-sm">{{ msg.role }}</span>
          <span class="mono text-xs" style="color: var(--text-muted)">{{ msg.participant }}</span>
        </div>
        <div class="mono text-xs" style="color: var(--text-secondary); white-space: pre-wrap">{{ msg.content }}</div>
      </div>
      <div v-if="round.verdict" class="verdict-card p-3 mt-2">
        <div class="text-sm font-bold">{{ round.verdict }}</div>
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref } from 'vue'

defineProps<{
  mode?: 'research' | 'risk'
  rounds?: Array<{ messages: Array<{ role: string; participant: string; content: string }>; verdict?: string }>
}>()

defineEmits<{ close: [] }>()

const visible = ref(true)
</script>

<style lang="scss" scoped>
.debate-msg {
  padding: 8px 12px;
  border-radius: 6px;
  background: var(--bg-root);
  border: 1px solid var(--border);

  &.bull {
    border-left: 3px solid #00a85a;
  }
  &.bear {
    border-left: 3px solid #e33545;
  }
  &.manager {
    border-left: 3px solid #2b6de5;
  }
}

.verdict-card {
  background: rgba(43, 109, 229, 0.06);
  border: 1px solid rgba(43, 109, 229, 0.2);
  border-radius: 8px;
  color: var(--accent-blue);
}
</style>
