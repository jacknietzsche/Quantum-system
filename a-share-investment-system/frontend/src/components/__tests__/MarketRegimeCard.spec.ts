import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import MarketRegimeCard from '../MarketRegimeCard.vue'

describe('MarketRegimeCard', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders BULL regime correctly', () => {
    const wrapper = mount(MarketRegimeCard, {
      props: {
        market: {
          regime: 'BULL',
          total_score: 0.75,
          dimension_scores: { momentum: 0.8, breadth: 0.6, sentiment: 0.5 },
          adaptive_params: { target_position_pct: 0.8, max_holdings: 10 },
        },
      },
    })

    expect(wrapper.text()).toContain('BULL MARKET')
    expect(wrapper.text()).toContain('Confidence')
    expect(wrapper.text()).toContain('Score')
    expect(wrapper.text()).toContain('momentum')
    expect(wrapper.text()).toContain('breadth')
  })

  it('renders BEAR regime with red styling', () => {
    const wrapper = mount(MarketRegimeCard, {
      props: {
        market: {
          regime: 'BEAR',
          total_score: -0.6,
          dimension_scores: {},
          adaptive_params: { target_position_pct: 0.3, max_holdings: 5 },
        },
      },
    })

    expect(wrapper.text()).toContain('BEAR MARKET')
    expect(wrapper.text()).toContain('HIGH') // risk level
  })

  it('handles null market gracefully', () => {
    const wrapper = mount(MarketRegimeCard, {
      props: { market: null },
    })

    expect(wrapper.text()).toContain('NEUTRAL')
  })

  it('renders dimension scores with correct color classes', () => {
    const wrapper = mount(MarketRegimeCard, {
      props: {
        market: {
          regime: 'NEUTRAL',
          total_score: 0.1,
          dimension_scores: { up_factor: 0.5, down_factor: -0.3 },
          adaptive_params: { target_position_pct: 0.5, max_holdings: 8 },
        },
      },
    })

    const upEl = wrapper.find('.num-up')
    const downEl = wrapper.find('.num-down')
    expect(upEl.exists()).toBe(true)
    expect(downEl.exists()).toBe(true)
  })

  it('displays position and max holdings from adaptive_params', () => {
    const wrapper = mount(MarketRegimeCard, {
      props: {
        market: {
          regime: 'NEUTRAL',
          total_score: 0,
          dimension_scores: {},
          adaptive_params: { target_position_pct: 0.6, max_holdings: 7 },
        },
      },
    })

    expect(wrapper.text()).toContain('60% target')
    expect(wrapper.text()).toContain('7 holdings')
  })
})
