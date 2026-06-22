import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import DailySummaryCard from '../DailySummaryCard.vue'

describe('DailySummaryCard', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders nothing when summary is null', () => {
    const wrapper = mount(DailySummaryCard, {
      props: { summary: null },
    })

    expect(wrapper.find('.daily-summary-card').exists()).toBe(false)
  })

  it('renders summary with date and metrics', () => {
    const wrapper = mount(DailySummaryCard, {
      props: {
        summary: {
          date: '2024-06-01',
          market_regime: 'BULL',
          risk_level: 'LOW',
          recommendations_count: 12,
          position_count: 5,
        },
      },
    })

    expect(wrapper.text()).toContain('2024-06-01')
    expect(wrapper.text()).toContain('BULL')
    expect(wrapper.text()).toContain('LOW')
    expect(wrapper.text()).toContain('12')
    expect(wrapper.text()).toContain('5')
  })

  it('renders top recommendations', () => {
    const wrapper = mount(DailySummaryCard, {
      props: {
        summary: {
          date: '2024-06-01',
          top_recommendations: [
            { stock_code: '600519', stock_name: 'Moutai', signal: '买入', score: 85 },
            { stock_code: '000001', stock_name: 'PingAn', signal: '持有', score: 72 },
          ],
        },
      },
    })

    expect(wrapper.text()).toContain('600519')
    expect(wrapper.text()).toContain('Moutai')
    expect(wrapper.text()).toContain('Top Picks')
    expect(wrapper.text()).toContain('85pts')
  })

  it('emits run-screening on button click', async () => {
    const wrapper = mount(DailySummaryCard, {
      props: {
        summary: { date: '2024-06-01' },
      },
    })

    await wrapper.find('.el-button').trigger('click')
    expect(wrapper.emitted('run-screening')).toBeTruthy()
  })

  it('handles missing optional fields gracefully', () => {
    const wrapper = mount(DailySummaryCard, {
      props: {
        summary: { date: '2024-06-01' },
      },
    })

    expect(wrapper.text()).toContain('2024-06-01')
    expect(wrapper.text()).toContain('?')
    expect(wrapper.text()).toContain('0')
  })

  it('limits recommendations to 5', () => {
    const recs = Array.from({ length: 10 }, (_, i) => ({
      stock_code: `${600000 + i}`,
      stock_name: `Stock${i}`,
      signal: '买入',
      score: 80 - i,
    }))

    const wrapper = mount(DailySummaryCard, {
      props: {
        summary: { date: '2024-06-01', top_recommendations: recs },
      },
    })

    const items = wrapper.findAll('.daily-rec-item')
    expect(items.length).toBeLessThanOrEqual(5)
  })
})
