import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import CompetencyList from '../CompetencyList.vue'
import CompetencyBadge from '../CompetencyBadge.vue'

const competencies = [
  { id: 1, name: 'Python' },
  { id: 2, name: 'TypeScript', description: 'Typed JS' },
  { id: 3, name: 'Docker', aliases: 'docker, container' }
]

describe('CompetencyList.vue', () => {
  it('rend autant de CompetencyBadge que de compétences', () => {
    const wrapper = mount(CompetencyList, { props: { competencies } })
    const badges = wrapper.findAllComponents(CompetencyBadge)
    expect(badges).toHaveLength(3)
  })

  it('utilise comp.id comme key si disponible', () => {
    const wrapper = mount(CompetencyList, { props: { competencies } })
    expect(wrapper.html()).toContain('Python')
    expect(wrapper.html()).toContain('TypeScript')
    expect(wrapper.html()).toContain('Docker')
  })

  it('n\'affiche rien si la liste est vide', () => {
    const wrapper = mount(CompetencyList, { props: { competencies: [] } })
    expect(wrapper.findAllComponents(CompetencyBadge)).toHaveLength(0)
  })

  it('a la classe competency-list sur l\'élément racine', () => {
    const wrapper = mount(CompetencyList, { props: { competencies } })
    expect(wrapper.find('.competency-list').exists()).toBe(true)
  })

  it('a le bon aria-label', () => {
    const wrapper = mount(CompetencyList, { props: { competencies } })
    expect(wrapper.find('[aria-label="Liste des compétences"]').exists()).toBe(true)
  })
})
