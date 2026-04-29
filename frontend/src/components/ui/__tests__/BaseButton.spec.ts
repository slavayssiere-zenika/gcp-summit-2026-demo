import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import BaseButton from '../BaseButton.vue'

describe('BaseButton.vue', () => {
  it('doit afficher le slot par défaut', () => {
    const wrapper = mount(BaseButton, {
      slots: {
        default: 'Cliquez-moi'
      }
    })
    expect(wrapper.text()).toContain('Cliquez-moi')
    expect(wrapper.classes()).toContain('base-btn')
    expect(wrapper.classes()).toContain('primary') // default variant
  })

  it('doit émettre un event click si non désactivé', async () => {
    const wrapper = mount(BaseButton)
    await wrapper.trigger('click')
    expect(wrapper.emitted()).toHaveProperty('click')
  })

  it('ne doit pas émettre un event click si disabled est vrai', async () => {
    const wrapper = mount(BaseButton, { props: { disabled: true } })
    await wrapper.trigger('click')
    expect(wrapper.emitted('click')).toBeUndefined()
  })

  it('doit afficher un spinner si loading est vrai', () => {
    const wrapper = mount(BaseButton, { props: { loading: true } })
    expect(wrapper.find('.spinner').exists()).toBe(true)
  })
})
