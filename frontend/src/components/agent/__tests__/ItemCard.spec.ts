import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import ItemCard from '../ItemCard.vue'

describe('ItemCard.vue', () => {
  it('doit afficher le nom de l\'item', () => {
    const wrapper = mount(ItemCard, {
      props: { item: { name: 'MacBook Pro M3' } }
    })
    expect(wrapper.text()).toContain('MacBook Pro M3')
  })

  it('doit afficher l\'id si présent', () => {
    const wrapper = mount(ItemCard, {
      props: { item: { id: 99, name: 'Écran 4K' } }
    })
    expect(wrapper.text()).toContain('99')
    expect(wrapper.find('.id-tag').exists()).toBe(true)
  })

  it('ne doit pas afficher l\'id si absent', () => {
    const wrapper = mount(ItemCard, {
      props: { item: { name: 'Item sans ID' } }
    })
    expect(wrapper.find('.id-tag').exists()).toBe(false)
  })

  it('doit afficher la description si présente', () => {
    const wrapper = mount(ItemCard, {
      props: { item: { name: 'Souris ergonomique', description: 'Souris sans fil avec trackpad intégré' } }
    })
    expect(wrapper.find('.description').exists()).toBe(true)
    expect(wrapper.text()).toContain('Souris sans fil')
  })

  it('ne doit pas afficher de description si absente', () => {
    const wrapper = mount(ItemCard, {
      props: { item: { name: 'Item sans description' } }
    })
    expect(wrapper.find('.description').exists()).toBe(false)
  })

  it('doit afficher les catégories en tableau', () => {
    const wrapper = mount(ItemCard, {
      props: { item: { name: 'Item', categories: ['Hardware', 'Apple'] } }
    })
    const tags = wrapper.findAll('.tag')
    expect(tags).toHaveLength(2)
    expect(wrapper.text()).toContain('Hardware')
    expect(wrapper.text()).toContain('Apple')
  })

  it('doit afficher une catégorie unique (non-tableau)', () => {
    const wrapper = mount(ItemCard, {
      props: { item: { name: 'Item', categories: 'Software' } }
    })
    expect(wrapper.findAll('.tag')).toHaveLength(1)
    expect(wrapper.text()).toContain('Software')
  })

  it('doit afficher les catégories objets (avec .name)', () => {
    const wrapper = mount(ItemCard, {
      props: { item: { name: 'Item', categories: [{ id: 1, name: 'Périphérique' }] } }
    })
    expect(wrapper.text()).toContain('Périphérique')
  })

  it('doit afficher le propriétaire si user_id est présent', () => {
    const wrapper = mount(ItemCard, {
      props: { item: { name: 'Item', user_id: 7 } }
    })
    expect(wrapper.find('.owner').exists()).toBe(true)
    expect(wrapper.text()).toContain('#7')
  })
})
