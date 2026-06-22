<template>
  <div class="favorites-page">
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-lg font-semibold">自选股</h1>
      <div class="flex gap-2">
        <el-input v-model="newCode" placeholder="输入代码添加" style="width: 200px" size="small" />
        <el-button type="primary" size="small" @click="addStock">添加</el-button>
      </div>
    </div>
    <el-table :data="stocks" style="width: 100%" @row-click="goAnalysis">
      <el-table-column prop="stock_code" label="代码" width="120">
        <template #default="{ row }"><span class="mono" style="color: var(--accent-blue)">{{ row.stock_code }}</span></template>
      </el-table-column>
      <el-table-column prop="stock_name" label="名称" />
      <el-table-column prop="current_price" label="最新价" width="120">
        <template #default="{ row }">{{ (row.current_price || 0).toFixed(2) }}</template>
      </el-table-column>
      <el-table-column prop="pe_ratio" label="市盈率" width="100">
        <template #default="{ row }">{{ (row.pe_ratio || '-').toFixed(2) }}</template>
      </el-table-column>
      <el-table-column prop="pb_ratio" label="市净率" width="100">
        <template #default="{ row }">{{ (row.pb_ratio || '-').toFixed(2) }}</template>
      </el-table-column>
      <el-table-column prop="change_pct" label="涨跌幅" width="100">
        <template #default="{ row }">
          <span :style="{ color: row.change_pct > 0 ? 'var(--el-color-success)' : row.change_pct < 0 ? 'var(--el-color-danger)' : '' }">
            {{ (row.change_pct || 0).toFixed(2) }}%
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="industry" label="行业" width="120">
        <template #default="{ row }">{{ row.industry || '-' }}</template>
      </el-table-column>
      <el-table-column prop="trend" label="趋势" width="100">
        <template #default="{ row }">{{ row.trend || '-' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="80">
        <template #default="{ row }">
          <el-button text size="small" type="danger" @click.stop="removeStock(row.stock_code)">
            <el-icon><Delete /></el-icon>
          </el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!stocks.length" description="暂无自选股，输入代码添加" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { favoritesApi } from '@/api/favorites'
import { ElMessage } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'

const router = useRouter()
const stocks = ref<any[]>([])
const newCode = ref('')

const loadList = async () => {
  try {
    const res = await favoritesApi.list()
    stocks.value = (res as any)?.data || []
  } catch (e) { console.error(e) }
}

const addStock = async () => {
  if (!newCode.value.trim()) return
  try {
    await favoritesApi.add({ stock_code: newCode.value.trim() })
    newCode.value = ''
    await loadList()
    ElMessage.success('添加成功')
  } catch { ElMessage.error('添加失败') }
}

const removeStock = async (code: string) => {
  try {
    await favoritesApi.remove(code)
    await loadList()
  } catch { ElMessage.error('删除失败') }
}

const goAnalysis = (row: any) => {
  router.push(`/analysis/single?stock_code=${row.stock_code}`)
}

onMounted(loadList)
</script>
