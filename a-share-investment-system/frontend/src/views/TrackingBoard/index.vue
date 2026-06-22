<template>
  <div class="tracking-board">
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-lg font-semibold">跟踪看板</h1>
      <el-button text @click="loadData"><el-icon><Refresh /></el-icon></el-button>
    </div>
    <el-row :gutter="16">
      <el-col v-for="item in positions" :key="item.code" :span="6">
        <el-card shadow="hover" class="mb-4">
          <div class="flex justify-between items-start">
            <div>
              <div class="font-bold">{{ item.name }}</div>
              <div class="mono text-xs" style="color: var(--text-muted)">{{ item.code }}</div>
            </div>
            <el-tag v-if="item.verdict" :type="item.verdict === 'bullish' ? 'success' : 'danger'" size="small">
              {{ item.verdict }}
            </el-tag>
          </div>
          <div class="mt-2">
            <div class="text-lg font-bold mono">{{ (item.price || 0).toFixed(2) }}</div>
            <div class="mono text-xs" :class="(item.change_pct || 0) >= 0 ? 'num-up' : 'num-down'">
              {{ (item.change_pct || 0) >= 0 ? '+' : '' }}{{ (item.change_pct || 0).toFixed(2) }}%
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
    <el-empty v-if="!positions.length" description="暂无持仓跟踪数据" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { get } from '@/api/request'
import { Refresh } from '@element-plus/icons-vue'

const positions = ref<any[]>([])

const loadData = async () => {
  try {
    const res = await get('/api/portfolio/holdings')
    positions.value = (res as any)?.positions?.map((p: any) => ({
      code: p.stock_code,
      name: p.stock_name,
      price: p.current_price,
      change_pct: p.profit_loss_pct,
      verdict: p.signal,
    })) || []
  } catch (e) {
    console.error(e)
  }
}
onMounted(loadData)
</script>
