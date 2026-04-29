import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { describe, it, expect, beforeEach } from 'vitest'
import { createRouter, createMemoryHistory } from 'vue-router'
import ToastNotification from '../ToastNotification.vue'
import { useUxStore } from '@/stores/uxStore'

vi.mock('@/stores/uxStore', () => {
  let store: any
  return {
    useUxStore: () => store || (store = {
      toasts: [],
      removeToast: vi.fn()
    })
  }
})

import { vi } from 'vitest'

describe('ToastNotification.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('doit afficher les toasts du store', () => {
    const store = useUxStore()
    store.toasts = [
      { id: 1, message: 'Sauvegardé avec succès', type: 'success' },
      { id: 2, message: 'Erreur réseau', type: 'error' }
    ]

    const wrapper = mount(ToastNotification, {
      global: {
        stubs: { Teleport: true }
      }
    })

    expect(wrapper.text()).toContain('Sauvegardé avec succès')
    expect(wrapper.text()).toContain('Erreur réseau')
    expect(wrapper.findAll('[role="alert"]')).toHaveLength(2)
  })

  it('doit appliquer la classe CSS du type', () => {
    const store = useUxStore()
    store.toasts = [{ id: 1, message: 'Attention !', type: 'warning' }]

    const wrapper = mount(ToastNotification, {
      global: { stubs: { Teleport: true } }
    })

    expect(wrapper.find('.toast--warning').exists()).toBe(true)
  })

  it('doit appeler removeToast au clic sur le bouton fermer', async () => {
    const store = useUxStore()
    store.toasts = [{ id: 42, message: 'Info', type: 'info' }]

    const wrapper = mount(ToastNotification, {
      global: { stubs: { Teleport: true } }
    })

    await wrapper.find('.toast-close').trigger('click')
    expect(store.removeToast).toHaveBeenCalledWith(42)
  })

  it('ne doit rien afficher si toasts est vide', () => {
    const store = useUxStore()
    store.toasts = []

    const wrapper = mount(ToastNotification, {
      global: { stubs: { Teleport: true } }
    })

    expect(wrapper.findAll('[role="alert"]')).toHaveLength(0)
  })
})
