import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import CompetencyBadge from '../CompetencyBadge.vue'

const baseComp = { id: 1, name: 'Python' }

describe('CompetencyBadge.vue', () => {
  it('affiche le nom de la compétence', () => {
    const wrapper = mount(CompetencyBadge, { props: { competency: baseComp } })
    expect(wrapper.text()).toContain('Python')
  })

  it('affiche la description si présente', () => {
    const wrapper = mount(CompetencyBadge, {
      props: { competency: { ...baseComp, description: 'Langage backend polyvalent' } }
    })
    expect(wrapper.text()).toContain('Langage backend polyvalent')
    expect(wrapper.find('.comp-desc').exists()).toBe(true)
  })

  it('n\'affiche pas la description si absente', () => {
    const wrapper = mount(CompetencyBadge, { props: { competency: baseComp } })
    expect(wrapper.find('.comp-desc').exists()).toBe(false)
  })

  it('affiche les aliases (string[])', () => {
    const wrapper = mount(CompetencyBadge, {
      props: { competency: { ...baseComp, aliases: ['py', 'python3'] } }
    })
    expect(wrapper.text()).toContain('py, python3')
    expect(wrapper.find('.comp-alias').exists()).toBe(true)
  })

  it('affiche les aliases (string simple)', () => {
    const wrapper = mount(CompetencyBadge, {
      props: { competency: { ...baseComp, aliases: 'py' } }
    })
    expect(wrapper.text()).toContain('py')
  })

  it('n\'affiche pas les aliases si absents', () => {
    const wrapper = mount(CompetencyBadge, { props: { competency: baseComp } })
    expect(wrapper.find('.comp-alias').exists()).toBe(false)
  })

  it('a la classe competency-badge sur l\'élément racine', () => {
    const wrapper = mount(CompetencyBadge, { props: { competency: baseComp } })
    expect(wrapper.find('.competency-badge').exists()).toBe(true)
  })

  it('ne plante pas avec un objet minimal (id + name)', () => {
    expect(() => mount(CompetencyBadge, { props: { competency: baseComp } })).not.toThrow()
  })
})
