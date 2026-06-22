import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAnalysisStore } from '../analysis'

describe('analysis store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('starts with idle state', () => {
    const store = useAnalysisStore()
    expect(store.currentJobId).toBeNull()
    expect(store.jobStatus).toBe('idle')
    expect(store.isAnalyzing).toBe(false)
    expect(store.agents).toEqual([])
    expect(store.progress).toBe(0)
  })

  it('setJob updates state to running', () => {
    const store = useAnalysisStore()
    store.setJob('job-123')
    expect(store.currentJobId).toBe('job-123')
    expect(store.jobStatus).toBe('running')
    expect(store.isAnalyzing).toBe(true)
  })

  it('updateAgentStatus modifies existing agent', () => {
    const store = useAnalysisStore()
    store.agents = [
      { id: 'agent-1', name: '巴菲特', team: 'value', status: 'pending' },
      { id: 'agent-2', name: '芒格', team: 'risk', status: 'pending' },
    ]
    store.updateAgentStatus('agent-1', 'completed', 'bullish')
    expect(store.agents[0].status).toBe('completed')
    expect(store.agents[0].verdict).toBe('bullish')
    expect(store.agents[1].status).toBe('pending')
  })

  it('updateAgentStatus does nothing for unknown agent', () => {
    const store = useAnalysisStore()
    store.agents = [{ id: 'agent-1', name: '巴菲特', team: 'value', status: 'pending' }]
    store.updateAgentStatus('unknown-id', 'completed')
    expect(store.agents[0].status).toBe('pending')
  })

  it('reset clears all state', () => {
    const store = useAnalysisStore()
    store.setJob('job-123')
    store.agents = [{ id: 'a1', name: 'A', team: 't', status: 'completed' }]
    store.progress = 80
    store.reset()
    expect(store.currentJobId).toBeNull()
    expect(store.jobStatus).toBe('idle')
    expect(store.isAnalyzing).toBe(false)
    expect(store.agents).toEqual([])
    expect(store.progress).toBe(0)
  })
})
