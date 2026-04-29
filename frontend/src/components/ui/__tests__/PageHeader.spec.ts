import { mount } from '@vue/test-utils'
import { describe, it, expect, vi } from 'vitest'
import { createRouter, createMemoryHistory } from 'vue-router'
import PageHeader from '../PageHeader.vue'

vi.mock('../../services/auth', () => ({
  authService: {
    state: { user: null }
  }
}))

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/', component: { template: '<div/>' } },
    { path: '/admin', component: { template: '<div/>' } }
  ]
})

describe('PageHeader.vue', () => {
  it('doit afficher le titre', () => {
    const wrapper = mount(PageHeader, {
      props: { title: 'Tableau de bord' },
      global: { plugins: [router] }
    })
    expect(wrapper.find('h1').text()).toBe('Tableau de bord')
  })

  it('doit afficher le sous-titre si fourni', () => {
    const wrapper = mount(PageHeader, {
      props: { title: 'Missions', subtitle: 'Gérez les missions clients' },
      global: { plugins: [router] }
    })
    expect(wrapper.find('p').text()).toContain('Gérez les missions clients')
  })

  it('ne doit pas afficher le sous-titre si absent', () => {
    const wrapper = mount(PageHeader, {
      props: { title: 'Profil' },
      global: { plugins: [router] }
    })
    expect(wrapper.find('p').exists()).toBe(false)
  })

  it('doit afficher le breadcrumb si fourni', () => {
    const wrapper = mount(PageHeader, {
      props: {
        title: 'Détail',
        breadcrumb: [
          { label: 'Accueil', to: '/' },
          { label: 'Mission Java' }
        ]
      },
      global: { plugins: [router] }
    })
    expect(wrapper.find('nav').exists()).toBe(true)
    expect(wrapper.text()).toContain('Accueil')
    expect(wrapper.text()).toContain('Mission Java')
  })

  it('ne doit pas afficher le breadcrumb si vide', () => {
    const wrapper = mount(PageHeader, {
      props: { title: 'Page', breadcrumb: [] },
      global: { plugins: [router] }
    })
    expect(wrapper.find('nav').exists()).toBe(false)
  })

  it('doit naviguer au clic sur un lien de breadcrumb', async () => {
    const pushSpy = vi.spyOn(router, 'push')
    const wrapper = mount(PageHeader, {
      props: {
        title: 'Admin',
        breadcrumb: [{ label: 'Retour', to: '/admin' }]
      },
      global: { plugins: [router] }
    })
    await wrapper.find('.crumb-link').trigger('click')
    expect(pushSpy).toHaveBeenCalledWith('/admin')
  })

  it('ne doit pas afficher le badge de rôle si showRole=false', () => {
    const wrapper = mount(PageHeader, {
      props: { title: 'Page', showRole: false },
      global: { plugins: [router] }
    })
    expect(wrapper.find('.role-badge').exists()).toBe(false)
  })
})
