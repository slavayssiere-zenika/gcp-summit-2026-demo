import { mount } from '@vue/test-utils'
import { describe, it, expect, vi } from 'vitest'
import { createRouter, createMemoryHistory } from 'vue-router'
import ConsultantAvailabilityCard from '../ConsultantAvailabilityCard.vue'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/', component: { template: '<div/>' } },
    { path: '/users/:id', name: 'user-detail', component: { template: '<div/>' } }
  ]
})

const availableData = {
  user_id: 5,
  is_available: true,
  conflict_detected: false,
  summary: 'Consultant disponible pour mission',
  active_missions: [],
  unavailability_periods: []
}

describe('ConsultantAvailabilityCard.vue', () => {
  it('doit afficher "Disponible" avec status-success', () => {
    const wrapper = mount(ConsultantAvailabilityCard, {
      props: { availability: availableData },
      global: { plugins: [router] }
    })
    expect(wrapper.text()).toContain('Disponible')
    expect(wrapper.find('.card-header.status-success').exists()).toBe(true)
  })

  it('doit afficher "Indisponible" avec status-warning', () => {
    const wrapper = mount(ConsultantAvailabilityCard, {
      props: { availability: { ...availableData, is_available: false } },
      global: { plugins: [router] }
    })
    expect(wrapper.text()).toContain('Indisponible')
    expect(wrapper.find('.card-header.status-warning').exists()).toBe(true)
  })

  it('doit afficher "Conflit Détecté" avec status-danger', () => {
    const wrapper = mount(ConsultantAvailabilityCard, {
      props: { availability: { ...availableData, conflict_detected: true } },
      global: { plugins: [router] }
    })
    expect(wrapper.text()).toContain('Conflit Détecté')
    expect(wrapper.find('.card-header.status-danger').exists()).toBe(true)
  })

  it('doit afficher le résumé', () => {
    const wrapper = mount(ConsultantAvailabilityCard, {
      props: { availability: availableData },
      global: { plugins: [router] }
    })
    expect(wrapper.find('.summary-text').text()).toBe('Consultant disponible pour mission')
  })

  it('doit afficher les missions actives si présentes', () => {
    const data = {
      ...availableData,
      active_missions: [{ mission_id: 42, workload_percentage: 80, status: 'IN_PROGRESS' }]
    }
    const wrapper = mount(ConsultantAvailabilityCard, {
      props: { availability: data },
      global: { plugins: [router] }
    })
    expect(wrapper.find('.detail-section').exists()).toBe(true)
    expect(wrapper.text()).toContain('Mission #42')
    expect(wrapper.text()).toContain('80%')
  })

  it('doit afficher les périodes d\'indisponibilité', () => {
    const data = {
      ...availableData,
      unavailability_periods: [{ type: 'Congé', start_date: '2025-07-01', end_date: '2025-07-14' }]
    }
    const wrapper = mount(ConsultantAvailabilityCard, {
      props: { availability: data },
      global: { plugins: [router] }
    })
    expect(wrapper.text()).toContain('Congé')
    expect(wrapper.text()).toContain('2025-07-01 au 2025-07-14')
  })

  it('doit afficher "Période non spécifiée" si les dates manquent', () => {
    const data = {
      ...availableData,
      unavailability_periods: [{ type: 'Autre' }]
    }
    const wrapper = mount(ConsultantAvailabilityCard, {
      props: { availability: data },
      global: { plugins: [router] }
    })
    expect(wrapper.text()).toContain('Période non spécifiée')
  })

  it('doit naviguer vers le profil utilisateur au clic', async () => {
    const pushSpy = vi.spyOn(router, 'push')
    const wrapper = mount(ConsultantAvailabilityCard, {
      props: { availability: availableData },
      global: { plugins: [router] }
    })
    await wrapper.find('.availability-card').trigger('click')
    expect(pushSpy).toHaveBeenCalledWith({ name: 'user-detail', params: { id: '5' } })
  })
})
