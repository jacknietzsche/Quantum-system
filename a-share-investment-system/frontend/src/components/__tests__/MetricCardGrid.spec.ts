import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import MetricCardGrid from '../MetricCardGrid.vue'

describe('MetricCardGrid', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders all four metric cards', () => {
    const wrapper = mount(MetricCardGrid, {
      props: {
        risk: { kill_switch: { active: false, daily_pnl_pct: 0.5 } },
        signals: { position_advice: { selection_threshold: '0.65', max_holdings: 8 }, top_factors: [{}, {}] },
        quality: 85,
        totalStocks: 5000,
      },
    })

    expect(wrapper.text()).toContain('Risk')
    expect(wrapper.text()).toContain('Strategy')
    expect(wrapper.text()).toContain('Factors')
    expect(wrapper.text()).toContain('Data Quality')
  })

  it('shows NOMINAL when kill switch is inactive', () => {
    const wrapper = mount(MetricCardGrid, {
      props: {
        risk: { kill_switch: { active: false, daily_pnl_pct: 0.3 } },
      },
    })

    expect(wrapper.text()).toContain('NOMINAL')
    expect(wrapper.text()).not.toContain('BREACHED')
  })

  it('shows BREACHED when kill switch is active', () => {
    const wrapper = mount(MetricCardGrid, {
      props: {
        risk: { kill_switch: { active: true, daily_pnl_pct: -5.2 } },
      },
    })

    expect(wrapper.text()).toContain('BREACHED')
  })

  it('displays factor count from top_factors', () => {
    const wrapper = mount(MetricCardGrid, {
      props: {
        signals: { top_factors: [{}, {}, {}] },
      },
    })

    expect(wrapper.text()).toContain('3')
    expect(wrapper.text()).toContain('Active')
  })

  it('handles missing props with defaults', () => {
    const wrapper = mount(MetricCardGrid, {
      props: {},
    })

    expect(wrapper.text()).toContain('NOMINAL')
    expect(wrapper.text()).toContain('0%')
    expect(wrapper.text()).toContain('--')
  })

  it('shows quality percentage', () => {
    const wrapper = mount(MetricCardGrid, {
      props: { quality: 92, totalStocks: 6000 },
    })

    expect(wrapper.text()).toContain('92')
    expect(wrapper.text()).toContain('6000')
  })
})
