import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import DecisionCard from '../DecisionCard.vue'

const globalStubs = {
  'el-tag': { template: '<span><slot />{{ $attrs.type }}</span>' },
  'el-progress': { template: '<div><slot />{{ $attrs.percentage }}</div>' },
  'el-collapse': { template: '<div><slot /></div>' },
  'el-collapse-item': { template: '<div>{{ $attrs.title }}<slot /></div>' },
}

describe('DecisionCard', () => {
  it('renders holding decision', () => {
    const wrapper = mount(DecisionCard, {
      props: { decision: 'hold' },
      global: { stubs: globalStubs },
    })
    expect(wrapper.text()).toContain('持有')
  })

  it('renders buy decision with confidence', () => {
    const wrapper = mount(DecisionCard, {
      props: { decision: 'buy', confidence: 85 },
      global: { stubs: globalStubs },
    })
    expect(wrapper.text()).toContain('买入')
    expect(wrapper.text()).toContain('85%')
  })

  it('renders sell decision', () => {
    const wrapper = mount(DecisionCard, {
      props: { decision: 'sell', confidence: 30 },
      global: { stubs: globalStubs },
    })
    expect(wrapper.text()).toContain('卖出')
  })

  it('shows target and stop prices', () => {
    const wrapper = mount(DecisionCard, {
      props: { targetPrice: 150, stopLoss: 120 },
      global: { stubs: globalStubs },
    })
    expect(wrapper.text()).toContain('150')
    expect(wrapper.text()).toContain('120')
  })

  it('shows reasoning text', () => {
    const wrapper = mount(DecisionCard, {
      props: { reasoning: 'PE估值偏低，安全边际充足' },
      global: { stubs: globalStubs },
    })
    expect(wrapper.text()).toContain('推理详情')
    expect(wrapper.text()).toContain('PE估值偏低，安全边际充足')
  })
})
