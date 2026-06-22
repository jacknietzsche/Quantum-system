<template>
  <div class="chat-copilot" style="display: flex; flex-direction: column; height: 100%">
    <div class="chat-messages flex-1 overflow-auto mb-3" ref="messagesRef">
      <div v-if="!messages.length" class="text-center py-8 mono text-sm" style="color: var(--text-muted)">
        输入股票代码或自然语言开始分析
      </div>
      <div v-for="(msg, i) in messages" :key="i" class="message mb-3" :class="msg.role">
        <div class="flex items-start gap-2">
          <el-avatar :size="28" :style="{ background: msg.role === 'user' ? 'var(--accent-blue)' : 'var(--accent-green)' }">
            {{ msg.role === 'user' ? 'U' : 'A' }}
          </el-avatar>
          <div class="msg-content flex-1">
            <div class="mono text-xs mb-1" style="color: var(--text-muted)">{{ msg.role === 'user' ? '你' : '助手' }}</div>
            <div class="mono text-sm" style="color: var(--text-primary); white-space: pre-wrap">{{ msg.content }}</div>
          </div>
        </div>
      </div>
    </div>
    <div class="chat-input flex gap-2">
      <el-input v-model="input" placeholder="输入股票代码或问题..." @keyup.enter="send" />
      <el-button type="primary" @click="send" :loading="loading">
        <el-icon><Promotion /></el-icon>
      </el-button>
    </div>
    <div class="presets flex gap-1 mt-2 flex-wrap">
      <el-tag v-for="p in presets" :key="p" size="small" class="cursor-pointer" @click="input = p; send()">{{ p }}</el-tag>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { Promotion } from '@element-plus/icons-vue'
import { get } from '@/api/request'

const input = ref('')
const loading = ref(false)
const messages = ref<Array<{ role: string; content: string }>>([])
const messagesRef = ref<HTMLElement>()
const presets = ['分析 600519', '分析 000858', '今天市场如何', '推荐股票']

const scrollBottom = () => nextTick(() => {
  if (messagesRef.value) messagesRef.value.scrollTop = messagesRef.value.scrollHeight
})

const send = async () => {
  const text = input.value.trim()
  if (!text || loading.value) return
  messages.value.push({ role: 'user', content: text })
  input.value = ''
  loading.value = true
  scrollBottom()

  try {
    const codeMatch = text.match(/(\d{6})/)
    if (codeMatch) {
      const res = await get(`/api/analysis/${codeMatch[1]}`)
      messages.value.push({ role: 'assistant', content: JSON.stringify(res, null, 2).slice(0, 1000) })
    } else {
      messages.value.push({ role: 'assistant', content: '请输入股票代码（6位数字）进行分析。' })
    }
  } catch (e: any) {
    ElMessage.error('分析请求失败')
    messages.value.push({ role: 'assistant', content: `错误: ${e.message}` })
  } finally {
    loading.value = false
    scrollBottom()
  }
}
</script>

<style lang="scss" scoped>
.message {
  .msg-content {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px 14px;
  }

  &.user .msg-content {
    border-color: rgba(43, 109, 229, 0.3);
  }
}

.cursor-pointer {
  cursor: pointer;
  &:hover { opacity: 0.8; }
}
</style>
