<template>
  <div class="risk-monitor">
    <el-card>
      <template #header>
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <el-icon><Lock /></el-icon>
            <span class="font-semibold">风险监控</span>
          </div>
          <el-tag :type="riskStatus.type" size="small">{{ riskStatus.label }}</el-tag>
        </div>
      </template>
      
      <div class="risk-grid">
        <div class="risk-item">
          <div class="risk-header">
            <span class="risk-label">最大回撤</span>
            <el-tag :type="getRiskType(risk.max_drawdown)" size="small">
              {{ risk.max_drawdown || 0 }}%
            </el-tag>
          </div>
          <el-progress :percentage="risk.max_drawdown || 0" :color="getProgressColor(risk.max_drawdown)" :stroke-width="8" />
        </div>
        
        <div class="risk-item">
          <div class="risk-header">
            <span class="risk-label">波动率</span>
            <el-tag :type="getRiskType(risk.volatility)" size="small">
              {{ risk.volatility || 0 }}%
            </el-tag>
          </div>
          <el-progress :percentage="risk.volatility || 0" :color="getProgressColor(risk.volatility)" :stroke-width="8" />
        </div>
        
        <div class="risk-item">
          <div class="risk-header">
            <span class="risk-label">VaR (95%)</span>
            <el-tag :type="getRiskType(risk.var_95)" size="small">
              {{ risk.var_95 || 0 }}%
            </el-tag>
          </div>
          <el-progress :percentage="risk.var_95 || 0" :color="getProgressColor(risk.var_95)" :stroke-width="8" />
        </div>
        
        <div class="risk-item">
          <div class="risk-header">
            <span class="risk-label">夏普比率</span>
            <el-tag :type="risk.sharpe_ratio >= 1 ? 'success' : 'warning'" size="small">
              {{ risk.sharpe_ratio?.toFixed(2) || '0.00' }}
            </el-tag>
          </div>
          <el-progress :percentage="Math.min((risk.sharpe_ratio || 0) * 20, 100)" :color="risk.sharpe_ratio >= 1 ? '#67c23a' : '#e6a23c'" :stroke-width="8" />
        </div>
      </div>
      
      <!-- 风险警报 -->
      <div class="alerts-section" v-if="alerts.length > 0">
        <h4>风险警报</h4>
        <div class="alerts-list">
          <div v-for="(alert, i) in alerts" :key="i" class="alert-item" :class="alert.level">
            <el-icon><Warning v-if="alert.level === 'warning'" /><CircleClose v-else-if="alert.level === 'danger'" /><CircleCheck v-else /></el-icon>
            <span>{{ alert.message }}</span>
          </div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { get } from '@/api/request'
import { Lock, Warning, CircleClose, CircleCheck } from '@element-plus/icons-vue'

const risk = ref<any>({
  max_drawdown: 0,
  volatility: 0,
  var_95: 0,
  sharpe_ratio: 0,
})

const alerts = ref<any[]>([])

const riskStatus = computed<{ type: 'success' | 'warning' | 'danger'; label: string }>(() => {
  const maxRisk = Math.max(risk.value.max_drawdown || 0, risk.value.volatility || 0)
  if (maxRisk > 20) return { type: 'danger', label: '高风险' }
  if (maxRisk > 10) return { type: 'warning', label: '中风险' }
  return { type: 'success', label: '低风险' }
})

const loadRiskData = async () => {
  try {
    const res = await get('/api/risk/status') as any
    if (res) {
      risk.value = {
        max_drawdown: res.max_drawdown || 5,
        volatility: res.volatility || 8,
        var_95: res.var_95 || 3,
        sharpe_ratio: res.sharpe_ratio || 1.2,
      }
      
      // Generate alerts based on risk levels
      alerts.value = []
      if (risk.value.max_drawdown > 15) {
        alerts.value.push({ level: 'danger', message: `最大回撤 ${risk.value.max_drawdown}% 超过阈值` })
      }
      if (risk.value.volatility > 15) {
        alerts.value.push({ level: 'warning', message: `波动率 ${risk.value.volatility}% 较高` })
      }
    }
  } catch (e) {
    console.error('Failed to load risk data:', e)
  }
}

const getRiskType = (value: number) => {
  if (value > 20) return 'danger'
  if (value > 10) return 'warning'
  return 'success'
}

const getProgressColor = (value: number) => {
  if (value > 20) return '#f56c6c'
  if (value > 10) return '#e6a23c'
  return '#67c23a'
}

onMounted(loadRiskData)
</script>

<style scoped>
.risk-monitor {
  margin-bottom: 20px;
}

.risk-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.risk-item {
  padding: 16px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
}

.risk-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.risk-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.alerts-section {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.alerts-section h4 {
  margin: 0 0 12px 0;
  font-size: 14px;
}

.alerts-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.alert-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 6px;
  font-size: 13px;
}

.alert-item.danger {
  background: #fef0f0;
  color: #f56c6c;
}

.alert-item.warning {
  background: #fdf6ec;
  color: #e6a23c;
}

.alert-item.success {
  background: #f0f9eb;
  color: #67c23a;
}
</style>