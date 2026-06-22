<template>
  <div class="task-center">
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-lg font-semibold">任务中心</h1>
      <el-button text @click="loadTasks"><el-icon><Refresh /></el-icon></el-button>
    </div>
    <el-tabs v-model="tab">
      <el-tab-pane label="进行中" name="running">
        <el-table :data="runningTasks">
          <el-table-column prop="stock_code" label="代码" width="100" />
          <el-table-column prop="stock_name" label="名称" />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag type="warning">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="start_time" label="开始时间" width="160" />
          <el-table-column label="操作" width="80">
            <template #default="{ row }">
              <el-button text size="small" type="danger" @click="cancelTask(row.task_id)">取消</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
      <el-tab-pane label="已完成" name="completed">
        <el-table :data="completedTasks" @row-click="goDetail">
          <el-table-column prop="stock_code" label="代码" width="100" />
          <el-table-column prop="stock_name" label="名称" />
          <el-table-column prop="start_time" label="完成时间" width="160" />
          <el-table-column label="操作" width="80">
            <template #default="{ row }">
              <el-button text size="small" @click.stop="goDetail(row)">查看</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { tasksApi } from '@/api/tasks'
import { analysisApi } from '@/api/analysis'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const router = useRouter()
const tab = ref('running')
const allTasks = ref<any[]>([])

const runningTasks = computed(() => allTasks.value.filter(t => t.status === 'running' || t.status === 'pending'))
const completedTasks = computed(() => allTasks.value.filter(t => t.status === 'completed'))

const loadTasks = async () => {
  try {
    const res = await analysisApi.getTaskList({ limit: 100 })
    allTasks.value = (res as any)?.tasks || []
  } catch (e) { console.error(e) }
}

const cancelTask = async (id: string) => {
  try {
    await analysisApi.cancelTask(id)
    await loadTasks()
    ElMessage.success('已取消')
  } catch { ElMessage.error('取消失败') }
}

const goDetail = (row: any) => {
  if (row.task_id) router.push(`/analysis/single?task_id=${row.task_id}`)
}

onMounted(loadTasks)
</script>
