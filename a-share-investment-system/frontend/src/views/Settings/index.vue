<template>
  <div class="settings-page">
    <!-- 系统设置 -->
    <el-card class="mb-4">
      <template #header>
        <div class="flex items-center gap-2">
          <el-icon><Setting /></el-icon>
          <span class="text-lg font-semibold">系统设置</span>
        </div>
      </template>
      <el-form label-width="120px">
        <el-form-item label="数据刷新间隔">
          <el-select v-model="refreshInterval">
            <el-option :value="15" label="15秒" />
            <el-option :value="30" label="30秒" />
            <el-option :value="60" label="60秒" />
          </el-select>
        </el-form-item>
        <el-form-item label="默认分析深度">
          <el-select v-model="analysisDepth">
            <el-option :value="1" label="浅度 (1轮)" />
            <el-option :value="3" label="中等 (3轮)" />
            <el-option :value="5" label="深度 (5轮)" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="saveSettings">保存设置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 邮箱设置 -->
    <EmailSettings />

    <!-- 关于系统 -->
    <el-card class="mt-4">
      <template #header>
        <div class="flex items-center gap-2">
          <el-icon><InfoFilled /></el-icon>
          <span class="text-lg font-semibold">关于系统</span>
        </div>
      </template>
      <div class="about-content">
        <div class="about-item">
          <span class="about-label">版本</span>
          <span class="about-value">AShare-X v4.0.0</span>
        </div>
        <div class="about-item">
          <span class="about-label">前端</span>
          <span class="about-value">Vue 3 + Element Plus</span>
        </div>
        <div class="about-item">
          <span class="about-label">后端</span>
          <span class="about-value">FastAPI + LangGraph</span>
        </div>
        <div class="about-item">
          <span class="about-label">数据源</span>
          <span class="about-value">AkShare / BaoStock / 东方财富</span>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Setting, InfoFilled } from '@element-plus/icons-vue'
import EmailSettings from './EmailSettings.vue'

const refreshInterval = ref(30)
const analysisDepth = ref(3)

onMounted(() => {
  const savedInterval = localStorage.getItem('refreshInterval')
  const savedDepth = localStorage.getItem('analysisDepth')
  if (savedInterval) refreshInterval.value = Number(savedInterval)
  if (savedDepth) analysisDepth.value = Number(savedDepth)
})

const saveSettings = () => {
  localStorage.setItem('refreshInterval', String(refreshInterval.value))
  localStorage.setItem('analysisDepth', String(analysisDepth.value))
  ElMessage.success('设置已保存')
}
</script>

<style scoped>
.settings-page {
  max-width: 900px;
  margin: 0 auto;
  padding: 20px;
}

.about-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.about-item {
  display: flex;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid var(--el-border-color-extra-light);
}

.about-item:last-child {
  border-bottom: none;
}

.about-label {
  width: 80px;
  color: var(--el-text-color-secondary);
}

.about-value {
  font-weight: 500;
  color: var(--el-text-color-primary);
}
</style>