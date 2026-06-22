<template>
  <div class="batch-analysis">
    <el-card>
      <template #header>
        <div class="flex items-center justify-between">
          <span class="text-lg font-semibold">批量分析</span>
        </div>
      </template>
      <div class="mb-4">
        <el-input
          v-model="stockCodes"
          type="textarea"
          :rows="4"
          placeholder="每行输入一个股票代码，如：&#10;600519&#10;000858&#10;601318"
        />
      </div>
      <el-button type="primary" @click="startBatch" :loading="loading">
        <el-icon><VideoPlay /></el-icon>
        批量分析 ({{ stockLines.length }} 只)
      </el-button>
      <el-table v-if="results.length" :data="results" class="mt-4">
        <el-table-column prop="stock_code" label="代码" width="100" />
        <el-table-column prop="signal" label="信号" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.signal" :type="row.signal === 'bullish' ? 'success' : row.signal === 'bearish' ? 'danger' : 'warning'" size="small">{{ row.signal }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="error" label="状态">
          <template #default="{ row }">{{ row.error || '完成' }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { analysisApi } from '@/api/analysis'
import { VideoPlay } from '@element-plus/icons-vue'

const stockCodes = ref('')
const loading = ref(false)
const results = ref<any[]>([])

const stockLines = computed(() => stockCodes.value.split('\n').map(s => s.trim()).filter(Boolean))

const startBatch = async () => {
  if (!stockLines.value.length) return
  loading.value = true
  results.value = []
  for (const code of stockLines.value) {
    try {
      const r = await analysisApi.getAnalysis(code)
      results.value.push({ stock_code: code, ...r })
    } catch (e: any) {
      results.value.push({ stock_code: code, error: e.message })
    }
  }
  loading.value = false
}
</script>
