<template>
  <div class="basic-layout">
    <nav class="sidebar" :class="{ collapsed: sidebarCollapsed }"
      @mouseenter="sidebarCollapsed = false"
      @mouseleave="sidebarCollapsed = true"
    >
      <div class="logo">
        <span class="logo-text">AX</span>
        <span class="logo-dot" />
      </div>

      <div class="menu-wrap">
        <el-menu
          :default-active="activeTab"
          :collapse="sidebarCollapsed"
          :router="true"
          background-color="transparent"
          text-color="var(--text-muted)"
          active-text-color="var(--accent-blue)"
        >
          <el-menu-item index="/dashboard">
            <el-icon><DataBoard /></el-icon>
            <span>总览</span>
          </el-menu-item>

          <el-sub-menu index="analysis">
            <template #title>
              <el-icon><TrendCharts /></el-icon>
              <span>分析</span>
            </template>
            <el-menu-item index="/analysis/single">单股分析</el-menu-item>
            <el-menu-item index="/analysis/batch">批量分析</el-menu-item>
            <el-menu-item index="/analysis/history">分析历史</el-menu-item>
          </el-sub-menu>

          <el-sub-menu index="/portfolio">
            <template #title>
              <el-icon><Briefcase /></el-icon>
              <span>持仓</span>
            </template>
            <el-menu-item index="/portfolio/limit_up">🔥 涨停狙击</el-menu-item>
            <el-menu-item index="/portfolio/momentum">📈 中期趋势</el-menu-item>
            <el-menu-item index="/portfolio/value">💎 长期价值</el-menu-item>
          </el-sub-menu>

          <el-menu-item index="/screening">
            <el-icon><Search /></el-icon>
            <span>选股</span>
          </el-menu-item>
          <el-menu-item index="/workflow">
            <el-icon><Cpu /></el-icon>
            <span>工作流</span>
          </el-menu-item>

          <el-menu-item index="/favorites">
            <el-icon><Star /></el-icon>
            <span>自选</span>
          </el-menu-item>

          <el-menu-item index="/reports">
            <el-icon><Document /></el-icon>
            <span>报告</span>
          </el-menu-item>

          <el-menu-item index="/tracking-board">
            <el-icon><Wallet /></el-icon>
            <span>跟踪看板</span>
          </el-menu-item>

          <el-menu-item index="/tasks">
            <el-icon><List /></el-icon>
            <span>任务</span>
          </el-menu-item>

          <!-- AI Memory -->
          <el-menu-item index="/ai/memory">
            <el-icon><Coin /></el-icon>
            <span>AI复盘</span>
          </el-menu-item>

          <el-menu-item index="/database">
            <el-icon><Folder /></el-icon>
            <span>数据库</span>
          </el-menu-item>

          <el-menu-item index="/logs">
            <el-icon><Tickets /></el-icon>
            <span>日志</span>
          </el-menu-item>

          <el-menu-item index="/settings">
            <el-icon><Setting /></el-icon>
            <span>设置</span>
          </el-menu-item>

          <el-menu-item index="/about">
            <el-icon><InfoFilled /></el-icon>
            <span>关于</span>
          </el-menu-item>
        </el-menu>
      </div>

      <div class="sidebar-footer" v-show="!sidebarCollapsed">
        <span class="version">v4.0.0</span>
      </div>
    </nav>

    <main class="main-content">
      <slot />
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import {
  DataBoard, TrendCharts, Briefcase, Search, Star,
  Document, Wallet, List, Folder, Tickets, Setting,
  InfoFilled, Coin, Cpu,
} from '@element-plus/icons-vue'

const route = useRoute()
const sidebarCollapsed = ref(true)

const activeTab = computed(() => {
  const path = route.path
  if (path.startsWith('/analysis')) return '/analysis/single'
  if (path.startsWith('/portfolio')) return '/portfolio/value'
  if (path.startsWith('/reports')) return '/reports'
  if (path.startsWith('/ai')) return '/ai/memory'
  return path
})
</script>

<style lang="scss" scoped>
.basic-layout {
  display: flex;
  height: 100vh;
  background: var(--bg-root);
}

.sidebar {
  position: relative;
  z-index: 1;
  width: 220px;
  background: var(--bg-card);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  transition: width 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
  flex-shrink: 0;

  &.collapsed {
    width: 56px;

    .logo-text { font-size: 13px; }
    .sidebar-footer { opacity: 0; }
  }

  .menu-wrap {
    flex: 1;
    overflow: hidden auto;
    padding: 4px 0;

    &::-webkit-scrollbar { width: 0; }
  }

  :deep(.el-menu) {
    border-right: none;
    background: transparent;

    .el-menu-item,
    .el-sub-menu__title {
      height: 42px;
      line-height: 42px;
      font-size: 13px;
      transition: all 0.18s;
      margin: 1px 8px;
      border-radius: 6px;
      width: auto;
      color: var(--text-secondary);

      &:hover {
        background: rgba(59, 130, 246, 0.06);
        color: var(--text-primary);
      }

      &.is-active {
        background: rgba(59, 130, 246, 0.10);
        color: var(--accent-blue);
        font-weight: 600;
        position: relative;

        .el-icon { color: var(--accent-blue); }

        &::after {
          content: '';
          position: absolute;
          left: -8px;
          top: 50%;
          transform: translateY(-50%);
          width: 2px;
          height: 18px;
          border-radius: 0 2px 2px 0;
          background: var(--accent-blue);
        }
      }
    }

    .el-sub-menu .el-menu {
      background: var(--bg-surface);
      border-radius: 6px;
      margin: 2px 8px;
      padding: 2px 0;

      .el-menu-item {
        padding-left: 48px !important;
        height: 34px;
        line-height: 34px;
        font-size: 12px;
      }
    }

    .el-sub-menu.is-opened > .el-sub-menu__title {
      color: var(--text-primary);
    }
  }
}

.logo {
  padding: 18px 0 14px;
  text-align: center;
  flex-shrink: 0;
  position: relative;

  &::after {
    content: '';
    display: block;
    margin: 14px auto 0;
    width: 28px;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(59, 130, 246, 0.2), transparent);
  }
}

.logo-text {
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 3px;
  background: linear-gradient(135deg, var(--accent-blue), var(--accent-cyan));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  font-family: 'JetBrains Mono', monospace;
}

.sidebar-footer {
  padding: 12px 0;
  text-align: center;
  flex-shrink: 0;
  transition: opacity 0.2s;
  border-top: 1px solid var(--border);

  .version {
    font-size: 10px;
    color: var(--text-muted);
    font-family: 'JetBrains Mono', monospace;
    letter-spacing: 1px;
  }
}

.main-content {
  position: relative;
  z-index: 1;
  flex: 1;
  overflow: auto;
  padding: 24px;
}
</style>
