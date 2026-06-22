import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface Agent {
  id: string
  name: string
  team: string
  status: 'pending' | 'in_progress' | 'completed' | 'skipped'
  verdict?: string
}

export interface AnalysisState {
  jobId: string | null
  status: string
  agents: Agent[]
  isAnalyzing: boolean
}

export const useAnalysisStore = defineStore('analysis', () => {
  const currentJobId = ref<string | null>(null)
  const jobStatus = ref<string>('idle')
  const isAnalyzing = ref(false)
  const agents = ref<Agent[]>([])
  const progress = ref(0)

  function setJob(jobId: string) {
    currentJobId.value = jobId
    jobStatus.value = 'running'
    isAnalyzing.value = true
  }

  function updateAgentStatus(agentId: string, status: Agent['status'], verdict?: string) {
    const agent = agents.value.find(a => a.id === agentId)
    if (agent) {
      agent.status = status
      if (verdict) agent.verdict = verdict
    }
  }

  function reset() {
    currentJobId.value = null
    jobStatus.value = 'idle'
    isAnalyzing.value = false
    agents.value = []
    progress.value = 0
  }

  return { currentJobId, jobStatus, isAnalyzing, agents, progress, setJob, updateAgentStatus, reset }
})
