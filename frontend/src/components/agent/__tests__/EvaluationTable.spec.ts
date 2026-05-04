import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import EvaluationTable from '../EvaluationTable.vue'
import EvaluationCard from '../EvaluationCard.vue'

const evaluations = [
  { competency_id: 1, competency_name: 'Python', ai_score: 4.0 },
  { competency_id: 2, competency_name: 'Docker', ai_score: 2.0 },
  { competency_id: 3, competency_name: 'Terraform', ai_score: null },
  { competency_id: 4, competency_name: 'Kubernetes', ai_score: 5.0 },
]

describe('EvaluationTable.vue', () => {
  it('rend autant de EvaluationCard que d\'évaluations', () => {
    const wrapper = mount(EvaluationTable, { props: { evaluations } })
    expect(wrapper.findAllComponents(EvaluationCard)).toHaveLength(4)
  })

  it('trie par ai_score décroissant (score le plus élevé en premier)', () => {
    const wrapper = mount(EvaluationTable, { props: { evaluations } })
    const cards = wrapper.findAllComponents(EvaluationCard)
    // Kubernetes (5.0) doit être premier, Python (4.0) deuxième
    expect(cards[0].props('evaluation').competency_name).toBe('Kubernetes')
    expect(cards[1].props('evaluation').competency_name).toBe('Python')
    expect(cards[2].props('evaluation').competency_name).toBe('Docker')
  })

  it('met les scores null en dernier', () => {
    const wrapper = mount(EvaluationTable, { props: { evaluations } })
    const cards = wrapper.findAllComponents(EvaluationCard)
    expect(cards[3].props('evaluation').competency_name).toBe('Terraform')
  })

  it('affiche un message vide si aucune évaluation', () => {
    const wrapper = mount(EvaluationTable, { props: { evaluations: [] } })
    expect(wrapper.findAllComponents(EvaluationCard)).toHaveLength(0)
    expect(wrapper.find('.eval-empty').exists()).toBe(true)
    expect(wrapper.text()).toContain('Aucune évaluation disponible')
  })

  it('a la classe evaluation-table sur l\'élément racine', () => {
    const wrapper = mount(EvaluationTable, { props: { evaluations } })
    expect(wrapper.find('.evaluation-table').exists()).toBe(true)
  })

  it('a le bon aria-label', () => {
    const wrapper = mount(EvaluationTable, { props: { evaluations } })
    expect(wrapper.find('[aria-label="Évaluations de compétences"]').exists()).toBe(true)
  })

  it('ne plante pas avec un seul élément', () => {
    const single = [{ competency_id: 1, competency_name: 'Python', ai_score: 3.5 }]
    expect(() => mount(EvaluationTable, { props: { evaluations: single } })).not.toThrow()
  })
})
