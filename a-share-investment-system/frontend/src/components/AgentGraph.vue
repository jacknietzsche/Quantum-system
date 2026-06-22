<template>
  <div class="agent-graph" ref="graphRef" style="width: 100%; height: 500px"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { VueFlow, useVueFlow } from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'

const props = defineProps<{
  agents?: Array<{ id: string; name: string; team: string; status: string; verdict?: string }>
}>()

const nodes = ref<any[]>([])
const edges = ref<any[]>([])

const teamColumns: Record<string, number> = {
  '分析师': 0, '研究员': 1, '交易员': 2, '风控': 3, '组合经理': 4,
}

function buildGraph() {
  const agents = props.agents || []
  const cols: Record<string, number> = {}
  let idx = 0
  agents.forEach(a => {
    const col = teamColumns[a.team] ?? 0
    const row = cols[col] ?? 0
    cols[col] = row + 1
    nodes.value.push({
      id: a.id,
      type: 'default',
      position: { x: col * 220 + 50, y: row * 100 + 50 },
      data: { label: `${a.name}\n${a.status}${a.verdict ? ` [${a.verdict}]` : ''}` },
      style: {
        background: a.status === 'completed' ? '#eefaf3' : a.status === 'in_progress' ? '#eef4ff' : '#f5f7fa',
        border: a.status === 'completed' ? '1px solid #00a85a' : a.status === 'in_progress' ? '1px solid #2b6de5' : '1px solid #d0d4dd',
        color: '#1a1a2e', padding: '10px 16px', borderRadius: 8, fontSize: 12, whiteSpace: 'pre-wrap',
      },
    })
  })
  // 添加边
  const ids = agents.map(a => a.id)
  for (let i = 1; i < ids.length; i++) {
    edges.value.push({ id: `e${i - 1}-${i}`, source: ids[i - 1], target: ids[i], animated: true, style: { stroke: '#d0d4dd' } })
  }
}

watch(() => props.agents, buildGraph, { deep: true })
onMounted(buildGraph)
</script>
