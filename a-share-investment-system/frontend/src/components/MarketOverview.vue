<template>
  <div class="market-overview">
    <el-card>
      <template #header>
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <el-icon><DataLine /></el-icon>
            <span class="font-semibold">市场概览</span>
          </div>
          <el-radio-group v-model="timeRange" size="small">
            <el-radio-button label="1w">1周</el-radio-button>
            <el-radio-button label="1m">1月</el-radio-button>
            <el-radio-button label="3m">3月</el-radio-button>
          </el-radio-group>
        </div>
      </template>
      <div ref="chartRef" style="height: 400px"></div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import * as echarts from 'echarts'
import { DataLine } from '@element-plus/icons-vue'

const chartRef = ref<HTMLElement>()
const timeRange = ref('1m')
let chart: echarts.ECharts | null = null

const initChart = () => {
  if (!chartRef.value) return
  
  chart = echarts.init(chartRef.value)
  
  // Generate sample data
  const dates: string[] = []
  const values: number[] = []
  const volumes: number[] = []
  const now = new Date()
  
  for (let i = 30; i >= 0; i--) {
    const date = new Date(now)
    date.setDate(date.getDate() - i)
    dates.push(date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }))
    values.push(3000 + Math.random() * 500)
    volumes.push(Math.random() * 1000000000)
  }
  
  chart.setOption({
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' }
    },
    legend: {
      data: ['上证指数', '成交量'],
      top: 0
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: dates,
      axisLine: { lineStyle: { color: '#999' } }
    },
    yAxis: [
      {
        type: 'value',
        name: '指数',
        position: 'left',
        axisLine: { lineStyle: { color: '#409eff' } },
        splitLine: { lineStyle: { type: 'dashed' } }
      },
      {
        type: 'value',
        name: '成交量',
        position: 'right',
        axisLine: { lineStyle: { color: '#67c23a' } },
        splitLine: { show: false }
      }
    ],
    series: [
      {
        name: '上证指数',
        type: 'line',
        data: values,
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#409eff', width: 2 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(64,158,255,0.3)' },
            { offset: 1, color: 'rgba(64,158,255,0.05)' }
          ])
        }
      },
      {
        name: '成交量',
        type: 'bar',
        yAxisIndex: 1,
        data: volumes,
        itemStyle: {
          color: (params: any) => {
            return params.dataIndex > 0 && values[params.dataIndex] > values[params.dataIndex - 1]
              ? '#67c23a'
              : '#f56c6c'
          }
        }
      }
    ]
  })
}

watch(timeRange, () => {
  // Update chart data based on time range
  if (chart) {
    chart.resize()
  }
})

onMounted(() => {
  initChart()
  window.addEventListener('resize', () => chart?.resize())
})
</script>

<style scoped>
.market-overview {
  margin-bottom: 20px;
}
</style>