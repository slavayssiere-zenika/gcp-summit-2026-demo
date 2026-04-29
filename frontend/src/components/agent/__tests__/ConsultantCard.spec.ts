import { mount } from '@vue/test-utils'
import { describe, it, expect, vi } from 'vitest'
import { createRouter, createMemoryHistory } from 'vue-router'
import ConsultantCard from '../ConsultantCard.vue'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/', component: { template: '<div/>' } },
    { path: '/users/:id', name: 'user-detail', component: { template: '<div/>' } }
  ]
})

const baseConsultant = {
  id: 12,
  full_name: 'Alice Martin',
  email: 'alice.martin@zenika.com',
  is_active: true
}

describe('ConsultantCard.vue', () => {
  it('doit afficher le nom et l\'email du consultant', () => {
    const wrapper = mount(ConsultantCard, {
      props: { consultant: baseConsultant },
      global: { plugins: [router] }
    })
    expect(wrapper.text()).toContain('Alice Martin')
    expect(wrapper.text()).toContain('alice.martin@zenika.com')
  })

  it('doit afficher le badge "Actif" si is_active est vrai', () => {
    const wrapper = mount(ConsultantCard, {
      props: { consultant: baseConsultant },
      global: { plugins: [router] }
    })
    expect(wrapper.find('.status-badge.active').exists()).toBe(true)
    expect(wrapper.text()).toContain('Actif')
  })

  it('doit afficher le badge "Inactif" si is_active est faux', () => {
    const wrapper = mount(ConsultantCard, {
      props: { consultant: { ...baseConsultant, is_active: false } },
      global: { plugins: [router] }
    })
    expect(wrapper.find('.status-badge.active').exists()).toBe(false)
    expect(wrapper.text()).toContain('Inactif')
  })

  it('doit afficher les initiales si pas de photo', () => {
    const wrapper = mount(ConsultantCard, {
      props: { consultant: baseConsultant },
      global: { plugins: [router] }
    })
    expect(wrapper.find('.avatar').text()).toContain('AM')
  })

  it('doit afficher "?" si le nom est absent', () => {
    const wrapper = mount(ConsultantCard, {
      props: { consultant: { id: 5 } },
      global: { plugins: [router] }
    })
    expect(wrapper.find('.avatar').text()).toContain('?')
  })

  it('doit afficher "Profil anonymisé" si is_anonymous', () => {
    const wrapper = mount(ConsultantCard, {
      props: { consultant: { ...baseConsultant, is_anonymous: true } },
      global: { plugins: [router] }
    })
    expect(wrapper.text()).toContain('Profil anonymisé')
    expect(wrapper.find('.email-row.anon').exists()).toBe(true)
  })

  it('doit afficher le badge Admin si role === admin', () => {
    const wrapper = mount(ConsultantCard, {
      props: { consultant: { ...baseConsultant, role: 'admin' } },
      global: { plugins: [router] }
    })
    expect(wrapper.find('.role-badge').exists()).toBe(true)
    expect(wrapper.text()).toContain('Admin')
  })

  it('ne doit pas afficher le badge Admin pour les autres rôles', () => {
    const wrapper = mount(ConsultantCard, {
      props: { consultant: { ...baseConsultant, role: 'consultant' } },
      global: { plugins: [router] }
    })
    expect(wrapper.find('.role-badge').exists()).toBe(false)
  })

  it('doit naviguer vers le profil au clic', async () => {
    const pushSpy = vi.spyOn(router, 'push')
    const wrapper = mount(ConsultantCard, {
      props: { consultant: baseConsultant },
      global: { plugins: [router] }
    })
    await wrapper.find('.consultant-card').trigger('click')
    expect(pushSpy).toHaveBeenCalledWith({ name: 'user-detail', params: { id: '12' } })
  })
})
