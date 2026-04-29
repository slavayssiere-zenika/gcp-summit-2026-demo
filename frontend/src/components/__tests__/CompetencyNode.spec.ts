import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import CompetencyNode from '../CompetencyNode.vue'

const leafNode = { id: 10, name: 'Python', sub_competencies: [] }
const parentNode = {
  id: 1,
  name: 'Backend',
  sub_competencies: [
    { id: 10, name: 'Python', sub_competencies: [] },
    { id: 11, name: 'Java', sub_competencies: [] }
  ]
}

describe('CompetencyNode.vue', () => {
  it('doit afficher le nom du nœud', () => {
    const wrapper = mount(CompetencyNode, { props: { node: leafNode } })
    expect(wrapper.text()).toContain('Python')
    expect(wrapper.text()).toContain('#10')
  })

  it('doit afficher l\'icône FileCode2 pour une feuille (sans enfants)', () => {
    const wrapper = mount(CompetencyNode, { props: { node: leafNode } })
    expect(wrapper.find('.node-header').classes()).toContain('is-leaf')
    expect(wrapper.find('.icon-toggle').exists()).toBe(false)
  })

  it('doit afficher l\'icône ChevronRight pour un nœud parent plié', () => {
    const wrapper = mount(CompetencyNode, { props: { node: parentNode } })
    expect(wrapper.find('.icon-toggle').exists()).toBe(true)
    // enfants non visibles initialement (fermé)
    expect(wrapper.find('.children').exists()).toBe(false)
  })

  it('doit déplier les enfants au clic si c\'est un nœud parent', async () => {
    const wrapper = mount(CompetencyNode, { props: { node: parentNode } })
    await wrapper.find('.node-header').trigger('click')
    expect(wrapper.find('.children').exists()).toBe(true)
  })

  it('doit replier les enfants au second clic', async () => {
    const wrapper = mount(CompetencyNode, { props: { node: parentNode } })
    await wrapper.find('.node-header').trigger('click')
    expect(wrapper.find('.children').exists()).toBe(true)
    await wrapper.find('.node-header').trigger('click')
    expect(wrapper.find('.children').exists()).toBe(false)
  })

  it('doit émettre select-leaf au clic sur une feuille', async () => {
    const wrapper = mount(CompetencyNode, { props: { node: leafNode } })
    await wrapper.find('.node-header').trigger('click')
    expect(wrapper.emitted('select-leaf')).toBeTruthy()
    expect(wrapper.emitted('select-leaf')![0]).toEqual([leafNode])
  })

  it('doit appliquer la classe is-root au depth 0', () => {
    const wrapper = mount(CompetencyNode, { props: { node: leafNode, depth: 0 } })
    expect(wrapper.find('.node-header').classes()).toContain('is-root')
  })

  it('ne doit pas appliquer is-root au depth > 0', () => {
    const wrapper = mount(CompetencyNode, { props: { node: leafNode, depth: 1 } })
    expect(wrapper.find('.node-header').classes()).not.toContain('is-root')
  })

  it('doit afficher la description si présente', () => {
    const node = { ...leafNode, description: 'Langage de programmation polyvalent' }
    const wrapper = mount(CompetencyNode, { props: { node } })
    expect(wrapper.find('.description').text()).toBe('Langage de programmation polyvalent')
  })

  it('doit afficher les alias si présents', () => {
    const node = { ...leafNode, aliases: 'Py, python3, cpython' }
    const wrapper = mount(CompetencyNode, { props: { node } })
    const badges = wrapper.findAll('.alias-badge')
    expect(badges.length).toBe(3)
    expect(badges[0].text()).toBe('Py')
  })

  it('doit rendre les enfants récursivement', async () => {
    const wrapper = mount(CompetencyNode, { props: { node: parentNode } })
    await wrapper.find('.node-header').trigger('click')
    // Les deux enfants doivent être présents
    const childNodes = wrapper.find('.children').findAll('.competency-node')
    expect(childNodes.length).toBe(2)
  })
})
