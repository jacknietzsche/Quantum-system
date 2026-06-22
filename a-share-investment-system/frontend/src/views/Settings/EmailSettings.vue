<template>
  <div class="email-settings">
    <el-card>
      <template #header>
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <el-icon><Message /></el-icon>
            <span class="text-lg font-semibold">邮箱设置</span>
          </div>
          <el-button type="primary" @click="saveSettings" :loading="saving">
            保存配置
          </el-button>
        </div>
      </template>

      <el-form :model="form" label-width="120px" label-position="top">
        <!-- 发送邮箱 -->
        <el-form-item label="发送邮箱 (QQ邮箱)">
          <el-input v-model="form.sender" placeholder="your_email@qq.com" clearable>
            <template #prefix>
              <el-icon><Message /></el-icon>
            </template>
          </el-input>
          <div class="form-tip">用于发送报告和通知的QQ邮箱地址</div>
        </el-form-item>

        <!-- 授权码 -->
        <el-form-item label="邮箱授权码">
          <el-input v-model="form.password" :type="showPassword ? 'text' : 'password'" placeholder="QQ邮箱授权码">
            <template #prefix>
              <el-icon><Lock /></el-icon>
            </template>
            <template #suffix>
              <el-icon @click="showPassword = !showPassword" style="cursor: pointer">
                <View v-if="showPassword" />
                <Hide v-else />
              </el-icon>
            </template>
          </el-input>
          <div class="form-tip">
            QQ邮箱 → 设置 → 账户 → POP3/SMTP服务 → 生成授权码
            <el-link type="primary" href="https://service.mail.qq.com/cgi-bin/help?subtype=1&&id=28&&no=1001256" target="_blank">
              查看教程
            </el-link>
          </div>
        </el-form-item>

        <!-- 发件人名称 -->
        <el-form-item label="发件人名称">
          <el-input v-model="form.sender_name" placeholder="A股智能投研系统" />
        </el-form-item>

        <!-- 收件人 -->
        <el-form-item label="收件人列表">
          <div class="receivers-list">
            <div v-for="(email, index) in form.receivers" :key="index" class="receiver-item">
              <el-input v-model="form.receivers[index]" placeholder="receiver@example.com" />
              <el-button type="danger" text @click="removeReceiver(index)">
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>
            <el-button type="primary" text @click="addReceiver" class="add-btn">
              <el-icon><Plus /></el-icon> 添加收件人
            </el-button>
          </div>
        </el-form-item>

        <!-- 测试邮件 -->
        <el-divider />
        <el-form-item label="测试邮件">
          <div class="flex gap-2 w-full">
            <el-input v-model="testEmail" placeholder="输入测试收件邮箱（可选）" clearable />
            <el-button type="success" @click="sendTest" :loading="testing">
              发送测试
            </el-button>
          </div>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 使用说明 -->
    <el-card class="mt-4">
      <template #header>
        <span class="font-semibold">使用说明</span>
      </template>
      <div class="help-content">
        <h4>QQ邮箱配置步骤：</h4>
        <ol>
          <li>登录 <el-link type="primary" href="https://mail.qq.com" target="_blank">QQ邮箱</el-link></li>
          <li>进入 设置 → 账户</li>
          <li>找到 POP3/SMTP/IMAP 服务</li>
          <li>开启 POP3/SMTP 服务</li>
          <li>生成授权码（需要短信验证）</li>
          <li>将授权码填入上方的"邮箱授权码"</li>
        </ol>
        <h4>功能说明：</h4>
        <ul>
          <li>分析报告完成后可一键发送邮件</li>
          <li>支持多个收件人</li>
          <li>报告以HTML格式发送，美观易读</li>
        </ul>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { get, post } from '@/api/request'
import { ElMessage } from 'element-plus'
import { Message, Lock, View, Hide, Delete, Plus } from '@element-plus/icons-vue'

const form = ref({
  sender: '',
  password: '',
  receivers: [] as string[],
  sender_name: 'A股智能投研系统',
})

const showPassword = ref(false)
const saving = ref(false)
const testing = ref(false)
const testEmail = ref('')

const loadSettings = async () => {
  try {
    const res = await get('/api/settings/email') as any
    if (res.ok && res.settings) {
      form.value = {
        sender: res.settings.sender || '',
        password: res.settings.password || '',
        receivers: res.settings.receivers?.length > 0 ? res.settings.receivers : [''],
        sender_name: res.settings.sender_name || 'A股智能投研系统',
      }
    }
  } catch (e) {
    console.error('Failed to load email settings:', e)
  }
}

const saveSettings = async () => {
  saving.value = true
  try {
    // Filter empty receivers
    const receivers = form.value.receivers.filter(r => r.trim())
    if (!form.value.sender) {
      ElMessage.warning('请填写发送邮箱')
      return
    }
    if (!form.value.password) {
      ElMessage.warning('请填写邮箱授权码')
      return
    }
    if (receivers.length === 0) {
      ElMessage.warning('请添加至少一个收件人')
      return
    }

    const res = await post('/api/settings/email', {
      ...form.value,
      receivers,
    }) as any

    if (res.ok) {
      ElMessage.success('邮箱配置已保存')
    } else {
      ElMessage.error(res.error || '保存失败')
    }
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

const addReceiver = () => {
  form.value.receivers.push('')
}

const removeReceiver = (index: number) => {
  form.value.receivers.splice(index, 1)
  if (form.value.receivers.length === 0) {
    form.value.receivers.push('')
  }
}

const sendTest = async () => {
  testing.value = true
  try {
    const res = await post('/api/settings/email/test', {
      to: testEmail.value || undefined,
    }) as any

    if (res.ok) {
      ElMessage.success(res.message || '测试邮件发送成功')
    } else {
      ElMessage.error(res.message || res.error || '测试邮件发送失败')
    }
  } catch (e) {
    ElMessage.error('测试邮件发送失败')
  } finally {
    testing.value = false
  }
}

onMounted(loadSettings)
</script>

<style scoped>
.email-settings {
  max-width: 800px;
  margin: 0 auto;
  padding: 20px;
}

.form-tip {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
  line-height: 1.5;
}

.receivers-list {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.receiver-item {
  display: flex;
  gap: 8px;
  align-items: center;
}

.receiver-item .el-input {
  flex: 1;
}

.add-btn {
  align-self: flex-start;
  margin-top: 4px;
}

.help-content {
  color: var(--el-text-color-regular);
  line-height: 1.8;
}

.help-content h4 {
  margin: 16px 0 8px;
  color: var(--el-text-color-primary);
}

.help-content h4:first-child {
  margin-top: 0;
}

.help-content ol,
.help-content ul {
  padding-left: 20px;
}

.help-content li {
  margin-bottom: 4px;
}
</style>