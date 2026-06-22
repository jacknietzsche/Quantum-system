import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import TradingSignals from '../TradingSignals.vue'

vi.mock('@/api/request', () => ({
  get: vi.fn().mockResolvedValue([]),
}))

const stubs = {
  'el-card': { template: '<div><slot name="header" /><slot /></div>' },
  'el-button': { template: '<button><slot /></button>' },
  'el-tag': { template: '<span><slot /></span>' },
  'el-icon': { template: '<span><slot /></span>' },
}

describe('TradingSignals', () => {
  it('renders empty state when no signals', () => {
    const wrapper = mount(TradingSignals, {
      global: { stubs },
    })
    expect(wrapper.text()).toContain('暂无交易信号')
  })

  it('renders signal list when signals provided', async () => {
    const wrapper = mount(TradingSignals, {
      global: { stubs },
    })
    const vm = wrapper.vm as any
    vm.signals = [
      {
        type: 'buy',
        stock_code: '600519',
        stock_name: '茅台',
        reason: 'PE低估',
        time: '2025-01-15',
        confidence: 85,
      },
      {
        type: 'sell',
        stock_code: '000001',
        stock_name: '平安银行',
        reason: '止损',
        time: '2025-01-15',
        confidence: 90,
      },
    ]
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('600519')
    expect(wrapper.text()).toContain('茅台')
    expect(wrapper.text()).toContain('PE低估')
    expect(wrapper.text()).toContain('平安银行')
  })

  it('renders signal metadata', async () => {
    const wrapper = mount(TradingSignals, {
      global: { stubs },
    })
    const vm = wrapper.vm as any
    vm.signals = [
      {
        type: 'hold',
        stock_code: '600036',
        stock_name: '招行',
        reason: '持有观望',
        time: '2025-06-01',
        confidence: 60,
      },
    ]
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('置信度')
    expect(wrapper.text()).toContain('60%')
    expect(wrapper.text()).toContain('2025-06-01')
  })
})
