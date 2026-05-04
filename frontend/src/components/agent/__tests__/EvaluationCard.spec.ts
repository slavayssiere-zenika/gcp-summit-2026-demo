import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import EvaluationCard from '../EvaluationCard.vue'

const baseEval = {
  competency_id: 42,
  competency_name: 'Kubernetes',
  ai_score: 3.5,
}

describe('EvaluationCard.vue', () => {
  it('affiche le nom de la compétence', () => {
    const wrapper = mount(EvaluationCard, { props: { evaluation: baseEval } })
    expect(wrapper.text()).toContain('Kubernetes')
  })

  it('affiche le score IA formaté', () => {
    const wrapper = mount(EvaluationCard, { props: { evaluation: baseEval } })
    expect(wrapper.text()).toContain('3.5/5')
  })

  it('affiche N/A si ai_score est null', () => {
    const wrapper = mount(EvaluationCard, {
      props: { evaluation: { ...baseEval, ai_score: null } }
    })
    expect(wrapper.text()).toContain('N/A')
  })

  it('affiche le user_score si présent', () => {
    const wrapper = mount(EvaluationCard, {
      props: { evaluation: { ...baseEval, user_score: 4 } }
    })
    expect(wrapper.text()).toContain('4/5')
    expect(wrapper.find('.user-score').exists()).toBe(true)
  })

  it('n\'affiche pas user-score si absent', () => {
    const wrapper = mount(EvaluationCard, { props: { evaluation: baseEval } })
    expect(wrapper.find('.user-score').exists()).toBe(false)
  })

  it('affiche la justification si présente', () => {
    const wrapper = mount(EvaluationCard, {
      props: { evaluation: { ...baseEval, ai_justification: 'Maîtrise confirmée en production.' } }
    })
    expect(wrapper.text()).toContain('Maîtrise confirmée en production.')
    expect(wrapper.find('.eval-justification').exists()).toBe(true)
  })

  it('n\'affiche pas la justification si absente', () => {
    const wrapper = mount(EvaluationCard, { props: { evaluation: baseEval } })
    expect(wrapper.find('.eval-justification').exists()).toBe(false)
  })

  it('affiche la version de scoring si présente', () => {
    const wrapper = mount(EvaluationCard, {
      props: { evaluation: { ...baseEval, scoring_version: 'v2' } }
    })
    expect(wrapper.text()).toContain('v2')
    expect(wrapper.find('.eval-version').exists()).toBe(true)
  })

  it('couleur verte pour score >= 4', () => {
    const wrapper = mount(EvaluationCard, {
      props: { evaluation: { ...baseEval, ai_score: 4.5 } }
    })
    const badge = wrapper.find('.ai-score')
    // jsdom normalise les couleurs hex en rgb()
    const style = badge.attributes('style') ?? ''
    expect(style).toContain('rgb(16, 185, 129)') // #10b981 en rgb
  })

  it('couleur rouge pour score < 2.5', () => {
    const wrapper = mount(EvaluationCard, {
      props: { evaluation: { ...baseEval, ai_score: 1.5 } }
    })
    const badge = wrapper.find('.ai-score')
    const style = badge.attributes('style') ?? ''
    expect(style).toContain('rgb(239, 68, 68)') // #ef4444 en rgb
  })
})
