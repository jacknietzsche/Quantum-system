<template>
  <div class="analysis-history">
    <el-card>
      <template #header>
        <div class="flex items-center justify-between">
          <span class="text-lg font-semibold">分析历史</span>
          <el-button text @click="loadTasks">
            <el-icon><Refresh /></el-icon>
          </el-button>
        </div>
      </template>
      <el-table :data="tasks" style="width: 100%" @row-click="goDetail">
        <el-table-column prop="stock_code" label="代码" width="100" />
        <el-table-column prop="stock_name" label="名称" width="120" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="start_time" label="时间" width="160" />
        <el-table-column label="操作">
          <template #default="{ row }">
            <el-button text size="small" @click.stop="goDetail(row)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { analysisApi } from '@/api/analysis'
import { Refresh } from '@element-plus/icons-vue'

const router = useRouter()
const tasks = ref<any[]>([])

const statusType = (s: string): 'success' | 'danger' | 'warning' | 'info' => {
  const map: Record<string, 'success' | 'danger' | 'warning' | 'info'> = { pending: 'info', running: 'warning', completed: 'success', failed: 'danger' }
  return map[s] || 'info'
}
const statusText = (s: string) => ({ pending: '等待中', running: '处理中', completed: '已完成', failed: '失败' })[s] || s

const goDetail = (row: any) => {
  if (row.task_id) router.push(`/analysis/single?task_id=${row.task_id}`)
}

const loadTasks = async () => {
  try {
    const res = await analysisApi.getTaskList({ limit: 50 })
    tasks.value = (res as any)?.tasks || []
  } catch (e) {
    console.error(e)
  }
}

onMounted(loadTasks)
</script>
