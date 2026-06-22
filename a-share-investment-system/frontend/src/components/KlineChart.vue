<template>
  <div class="kline-chart" ref="chartRef" style="width: 100%; height: 400px"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps<{
  data?: Array<{ date: string; open: number; close: number; high: number; low: number; volume: number }>
  symbol?: string
}>()

const chartRef = ref<HTMLElement>()
let chart: echarts.ECharts | null = null

function initChart() {
  if (!chartRef.value) return
  chart = echarts.init(chartRef.value)

  const dates = props.data?.map(d => d.date) || []
  const volumes = props.data?.map(d => d.volume) || []

  const option: echarts.EChartsOption = {
    backgroundColor: 'transparent',
    grid: [{ left: '10%', right: '10%', top: 50, height: '60%' }, { left: '10%', right: '10%', top: '75%', height: '15%' }],
    xAxis: [{ type: 'category', data: dates, axisLine: { lineStyle: { color: '#d0d4dd' } }, axisLabel: { color: '#9090a8', fontSize: 10 } },
      { type: 'category', gridIndex: 1, data: dates, axisLabel: { show: false }, axisLine: { show: false } }],
    yAxis: [{ scale: true, splitLine: { lineStyle: { color: '#e8ebf0' } }, axisLabel: { color: '#9090a8', fontSize: 10 } },
      { scale: true, gridIndex: 1, splitLine: { show: false }, axisLabel: { color: '#9090a8', fontSize: 10 } }],
    series: [
      { type: 'candlestick', data: props.data?.map(d => [d.open, d.close, d.low, d.high]),
        itemStyle: { color: '#00a85a', color0: '#e33545', borderColor: '#00a85a', borderColor0: '#e33545' } },
      { type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: volumes,
        itemStyle: { color: (p: any) => p.dataIndex > 0 && (props.data?.[p.dataIndex]?.close || 0) >= (props.data?.[p.dataIndex - 1]?.close || 0) ? '#00a85a' : '#e33545', opacity: 0.5 } },
    ],
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
  }
  chart.setOption(option)
}

watch(() => props.data, () => { if (chart) { chart.dispose(); initChart() } })
onMounted(initChart)
onUnmounted(() => chart?.dispose())
</script>
