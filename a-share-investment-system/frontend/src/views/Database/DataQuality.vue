<template>
  <div class="data-quality-page">
    <!-- 概览卡片 -->
    <el-row :gutter="16" class="mb-4">
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="stat-card">
            <div class="stat-value">{{ total }}</div>
            <div class="stat-label">总股票数</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="stat-card excellent">
            <div class="stat-value">{{ summary.excellent || 0 }}</div>
            <div class="stat-label">优秀字段</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="stat-card warning">
            <div class="stat-value">{{ summary.fair || 0 }}</div>
            <div class="stat-label">一般字段</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="stat-card danger">
            <div class="stat-value">{{ summary.poor || 0 }}</div>
            <div class="stat-label">差字段</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 数据质量图表 -->
    <el-card class="mb-4">
      <template #header>
        <div class="flex items-center justify-between">
          <span class="font-semibold">数据质量分布</span>
          <el-button @click="loadData" :loading="loading" size="small">刷新</el-button>
        </div>
      </template>
      <div ref="chartRef" style="height: 400px"></div>
    </el-card>

    <!-- 字段详情表格 -->
    <el-card class="mb-4">
      <template #header>
        <span class="font-semibold">字段质量详情</span>
      </template>
      <el-table :data="columns" stripe style="width: 100%" :default-sort="{ prop: 'empty_pct', order: 'descending' }">
        <el-table-column prop="column" label="字段名" width="180" />
        <el-table-column prop="total" label="总数" width="80" />
        <el-table-column prop="non_empty" label="有效数" width="80" />
        <el-table-column prop="empty_count" label="空值数" width="80" />
        <el-table-column prop="empty_pct" label="空值率" width="100" sortable>
          <template #default="{ row }">
            <el-tag :type="getQualityType(row.quality)" size="small">
              {{ row.empty_pct }}%
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="质量" width="100">
          <template #default="{ row }">
            <el-tag :type="getQualityType(row.quality)" size="small">
              {{ getQualityLabel(row.quality) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="完整度">
          <template #default="{ row }">
            <el-progress :percentage="100 - row.empty_pct" :color="getProgressColor(row.quality)" :stroke-width="10" />
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 空数据股票 -->
    <el-card>
      <template #header>
        <div class="flex items-center justify-between">
          <span class="font-semibold">数据最空的股票 (Top 50)</span>
          <el-button @click="loadEmptyStocks" :loading="emptyLoading" size="small">刷新</el-button>
        </div>
      </template>
      <el-table :data="emptyStocks" stripe style="width: 100%">
        <el-table-column prop="stock_code" label="代码" width="100" />
        <el-table-column prop="stock_name" label="名称" width="120" />
        <el-table-column prop="empty_count" label="空字段数" width="100" />
        <el-table-column prop="total_fields" label="总字段数" width="100" />
        <el-table-column prop="empty_pct" label="空值率" width="100" sortable>
          <template #default="{ row }">
            <el-tag type="danger" size="small">{{ row.empty_pct }}%</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="完整度">
          <template #default="{ row }">
            <el-progress :percentage="100 - row.empty_pct" color="#f56c6c" :stroke-width="10" />
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { get } from '@/api/request'
import * as echarts from 'echarts'

const chartRef = ref<HTMLElement>()
const loading = ref(false)
const emptyLoading = ref(false)
const total = ref(0)
const summary = ref<any>({})
const columns = ref<any[]>([])
const emptyStocks = ref<any[]>([])

const loadData = async () => {
  loading.value = true
  try {
    const res = await get('/api/data-quality/quality-report') as any
    if (res.ok) {
      total.value = res.total
      summary.value = res.summary
      columns.value = res.columns || []
      await nextTick()
      renderChart()
    }
  } catch (e) {
    console.error('Failed to load data quality:', e)
  } finally {
    loading.value = false
  }
}

const loadEmptyStocks = async () => {
  emptyLoading.value = true
  try {
    const res = await get('/api/data-quality/empty-stocks?limit=50') as any
    if (res.ok) {
      emptyStocks.value = res.stocks || []
    }
  } catch (e) {
    console.error('Failed to load empty stocks:', e)
  } finally {
    emptyLoading.value = false
  }
}

const renderChart = () => {
  if (!chartRef.value) return
  
  const chart = echarts.init(chartRef.value)
  
  // Prepare data for bar chart
  const topColumns = columns.value.slice(0, 20)
  const names = topColumns.map(c => c.column)
  const values = topColumns.map(c => 100 - c.empty_pct)
  const colors = topColumns.map(c => {
    if (c.quality === 'excellent') return '#67c23a'
    if (c.quality === 'good') return '#409eff'
    if (c.quality === 'fair') return '#e6a23c'
    return '#f56c6c'
  })
  
  chart.setOption({
    title: { text: '字段完整度 (Top 20)', left: 'center' },
    tooltip: { 
      trigger: 'axis',
      formatter: (params: any) => {
        const p = params[0]
        return `${p.name}<br/>完整度: ${p.value}%`
      }
    },
    xAxis: { 
      type: 'category', 
      data: names,
      axisLabel: { rotate: 45, fontSize: 10 }
    },
    yAxis: { 
      type: 'value', 
      max: 100,
      axisLabel: { formatter: '{value}%' }
    },
    series: [{
      type: 'bar',
      data: values.map((v, i) => ({
        value: v,
        itemStyle: { color: colors[i] }
      })),
      label: { show: false }
    }]
  })
}

const getQualityType = (quality: string) => {
  if (quality === 'excellent') return 'success'
  if (quality === 'good') return 'primary'
  if (quality === 'fair') return 'warning'
  return 'danger'
}

const getQualityLabel = (quality: string) => {
  if (quality === 'excellent') return '优秀'
  if (quality === 'good') return '良好'
  if (quality === 'fair') return '一般'
  return '差'
}

const getProgressColor = (quality: string) => {
  if (quality === 'excellent') return '#67c23a'
  if (quality === 'good') return '#409eff'
  if (quality === 'fair') return '#e6a23c'
  return '#f56c6c'
}

onMounted(() => {
  loadData()
  loadEmptyStocks()
})
</script>

<style scoped>
.data-quality-page {
  padding: 20px;
}

.stat-card {
  text-align: center;
  padding: 10px 0;
}

.stat-value {
  font-size: 32px;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
  color: var(--el-text-color-primary);
}

.stat-label {
  font-size: 14px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}

.stat-card.excellent .stat-value {
  color: #67c23a;
}

.stat-card.warning .stat-value {
  color: #e6a23c;
}

.stat-card.danger .stat-value {
  color: #f56c6c;
}
</style>