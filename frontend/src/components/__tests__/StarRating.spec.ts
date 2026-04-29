import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import StarRating from '../StarRating.vue'

describe('StarRating.vue', () => {
  it('doit afficher 5 boutons étoile', () => {
    const wrapper = mount(StarRating, { props: { modelValue: 3 } })
    const buttons = wrapper.findAll('.star-btn')
    expect(buttons).toHaveLength(5)
  })

  it('doit appliquer la classe star--full aux étoiles en dessous de la valeur', () => {
    const wrapper = mount(StarRating, { props: { modelValue: 3 } })
    const icons = wrapper.findAll('.star-icon')
    expect(icons[0].classes()).toContain('star--full') // étoile 1
    expect(icons[1].classes()).toContain('star--full') // étoile 2
    expect(icons[2].classes()).toContain('star--full') // étoile 3
    expect(icons[3].classes()).toContain('star--empty') // étoile 4
    expect(icons[4].classes()).toContain('star--empty') // étoile 5
  })

  it('doit appliquer la classe star--half pour une demi-étoile', () => {
    const wrapper = mount(StarRating, { props: { modelValue: 2.5 } })
    const icons = wrapper.findAll('.star-icon')
    expect(icons[1].classes()).toContain('star--full')  // étoile 2
    expect(icons[2].classes()).toContain('star--half')  // étoile 3 (demi)
    expect(icons[3].classes()).toContain('star--empty') // étoile 4
  })

  it('doit émettre update:modelValue au clic sur une étoile', async () => {
    const wrapper = mount(StarRating, { props: { modelValue: 0 } })
    await wrapper.findAll('.star-btn')[2].trigger('click')
    expect(wrapper.emitted('update:modelValue')).toBeTruthy()
    expect(wrapper.emitted('update:modelValue')![0]).toEqual([3])
  })

  it('ne doit pas émettre en mode readonly', async () => {
    const wrapper = mount(StarRating, { props: { modelValue: 3, readonly: true } })
    await wrapper.findAll('.star-btn')[4].trigger('click')
    expect(wrapper.emitted('update:modelValue')).toBeFalsy()
  })

  it('doit appliquer la taille via la prop size', () => {
    const wrapper = mount(StarRating, { props: { modelValue: 0, size: 'lg' } })
    expect(wrapper.find('.star-rating').classes()).toContain('star-rating--lg')
  })
})
