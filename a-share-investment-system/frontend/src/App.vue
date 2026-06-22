<template>
  <div id="app" class="app-container">
    <BasicLayout>
      <router-view v-slot="{ Component, route }">
        <transition name="fade" mode="out-in">
          <keep-alive :include="keepAliveComponents">
            <component :is="Component" :key="route?.fullPath || 'default'" />
          </keep-alive>
        </transition>
      </router-view>
    </BasicLayout>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import BasicLayout from '@/layouts/BasicLayout.vue'

const keepAliveComponents = computed(() => [
  'Dashboard',
  'Portfolio',
  'Screening',
  'Favorites',
])
</script>

<style lang="scss">
.app-container {
  min-height: 100vh;
  background-color: var(--el-bg-color-page);
  transition: background-color 0.3s ease;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
