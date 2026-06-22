import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAppStore = defineStore('app', () => {
  const sidebarCollapsed = ref(false)
  const theme = ref<'dark' | 'light'>('dark')
  const loading = ref(false)

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  function setLoading(v: boolean) {
    loading.value = v
  }

  return { sidebarCollapsed, theme, loading, toggleSidebar, setLoading }
})
