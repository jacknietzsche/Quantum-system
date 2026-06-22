<template>
  <div class="trading-signals">
    <el-card>
      <template #header>
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <el-icon><Bell /></el-icon>
            <span class="font-semibold">交易信号</span>
          </div>
          <el-button @click="refreshSignals" :loading="loading" size="small" text>
            <el-icon><Refresh /></el-icon>
          </el-button>
        </div>
      </template>
      
      <div v-if="signals.length > 0" class="signals-list">
        <div v-for="(signal, index) in signals" :key="index" class="signal-item" :class="signal.type">
          <div class="signal-icon">
            <el-icon :size="20">
              <Top v-if="signal.type === 'buy'" />
              <Bottom v-else-if="signal.type === 'sell'" />
              <Minus v-else />
            </el-icon>
          </div>
          <div class="signal-content">
            <div class="signal-header">
              <span class="signal-stock">{{ signal.stock_code }}</span>
              <span class="signal-name">{{ signal.stock_name }}</span>
              <el-tag :type="getSignalTagType(signal.type)" size="small">
                {{ getSignalLabel(signal.type) }}
              </el-tag>
            </div>
            <div class="signal-reason">{{ signal.reason }}</div>
            <div class="signal-meta">
              <span class="signal-time">{{ signal.time }}</span>
              <span class="signal-confidence">置信度: {{ signal.confidence }}%</span>
            </div>
          </div>
        </div>
      </div>
      
      <div v-else class="empty-state">
        <el-icon :size="48"><Bell /></el-icon>
        <p>暂无交易信号</p>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { get } from '@/api/request'
import { Bell, Refresh, Top, Bottom, Minus } from '@element-plus/icons-vue'

const loading = ref(false)
const signals = ref<any[]>([])

const refreshSignals = async () => {
  loading.value = true
  try {
    const res = await get('/api/signals/today') as any
    if (res.top_factors) {
      // Transform factors into signals
      signals.value = res.top_factors.slice(0, 5).map((f: any, i: number) => ({
        stock_code: f.code || `Factor-${i+1}`,
        stock_name: f.name || f.factor_name,
        type: f.score > 0 ? 'buy' : f.score < 0 ? 'sell' : 'hold',
        reason: f.category || '市场因子',
        time: new Date().toLocaleTimeString('zh-CN'),
        confidence: Math.abs(f.score * 10).toFixed(0),
      }))
    }
  } catch (e) {
    console.error('Failed to load signals:', e)
  } finally {
    loading.value = false
  }
}

const getSignalTagType = (type: string) => {
  if (type === 'buy') return 'success'
  if (type === 'sell') return 'danger'
  return 'warning'
}

const getSignalLabel = (type: string) => {
  if (type === 'buy') return '买入'
  if (type === 'sell') return '卖出'
  return '持有'
}

onMounted(refreshSignals)
</script>

<style scoped>
.trading-signals {
  margin-bottom: 20px;
}

.signals-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.signal-item {
  display: flex;
  gap: 12px;
  padding: 16px;
  border-radius: 8px;
  background: var(--el-fill-color-light);
  transition: all 0.2s;
}

.signal-item:hover {
  background: var(--el-fill-color);
}

.signal-item.buy {
  border-left: 3px solid #67c23a;
}

.signal-item.sell {
  border-left: 3px solid #f56c6c;
}

.signal-item.hold {
  border-left: 3px solid #e6a23c;
}

.signal-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: var(--el-bg-color);
}

.signal-item.buy .signal-icon {
  color: #67c23a;
}

.signal-item.sell .signal-icon {
  color: #f56c6c;
}

.signal-item.hold .signal-icon {
  color: #e6a23c;
}

.signal-content {
  flex: 1;
}

.signal-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.signal-stock {
  font-weight: 600;
  font-family: 'JetBrains Mono', monospace;
}

.signal-name {
  color: var(--el-text-color-secondary);
}

.signal-reason {
  font-size: 13px;
  color: var(--el-text-color-regular);
  margin-bottom: 4px;
}

.signal-meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.empty-state {
  text-align: center;
  padding: 40px 0;
  color: var(--el-text-color-secondary);
}

.empty-state p {
  margin-top: 12px;
}
</style>