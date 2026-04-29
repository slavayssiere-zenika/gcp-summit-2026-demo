import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import FinopsBadge from '../FinopsBadge.vue'

describe('FinopsBadge.vue', () => {
  it('doit afficher le badge cache sémantique si semanticCacheHit', () => {
    const wrapper = mount(FinopsBadge, {
      props: { semanticCacheHit: true }
    })
    expect(wrapper.text()).toContain('Semantic Cache')
    expect(wrapper.text()).toContain('0 tokens')
    expect(wrapper.text()).toContain('$0.000000')
    expect(wrapper.find('.cost-badge--cache').exists()).toBe(true)
  })

  it('doit afficher les tokens et le coût LLM si usage présent', () => {
    const usage = {
      total_input_tokens: 1500,
      total_output_tokens: 500,
      estimated_cost_usd: 0.000042
    }
    const wrapper = mount(FinopsBadge, { props: { usage } })
    expect(wrapper.text()).toContain('2000 tokens')
    expect(wrapper.text()).toContain('$0.000042')
    expect(wrapper.find('.cost-badge--cache').exists()).toBe(false)
  })

  it('doit calculer 0 tokens si usage est vide', () => {
    const wrapper = mount(FinopsBadge, {
      props: { usage: { total_input_tokens: 0, total_output_tokens: 0, estimated_cost_usd: 0 } }
    })
    expect(wrapper.text()).toContain('0 tokens')
    expect(wrapper.text()).toContain('$0.000000')
  })

  it('ne doit rien afficher si pas de props', () => {
    const wrapper = mount(FinopsBadge, { props: {} })
    expect(wrapper.find('.cost-badge').exists()).toBe(false)
  })

  it('doit afficher le badge hallucination si un step GUARDRAIL est présent', () => {
    const steps = [
      { type: 'warning', tool: 'GUARDRAIL', args: { message: 'Données non vérifiées' } }
    ]
    const usage = { total_input_tokens: 100, total_output_tokens: 50, estimated_cost_usd: 0.000001 }
    const wrapper = mount(FinopsBadge, { props: { usage, steps } })

    expect(wrapper.find('.cost-badge--hallucination').exists()).toBe(true)
    expect(wrapper.find('.hallucination-label').exists()).toBe(true)
    expect(wrapper.text()).toContain('Hallucination')
  })

  it('ne doit pas afficher le badge hallucination pour des steps normaux', () => {
    const steps = [
      { type: 'call', tool: 'list_missions', args: {} },
      { type: 'result', data: {} }
    ]
    const usage = { total_input_tokens: 100, total_output_tokens: 50, estimated_cost_usd: 0.000001 }
    const wrapper = mount(FinopsBadge, { props: { usage, steps } })

    expect(wrapper.find('.cost-badge--hallucination').exists()).toBe(false)
  })
})
