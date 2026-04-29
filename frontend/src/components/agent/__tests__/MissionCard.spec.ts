import { mount } from '@vue/test-utils'
import { describe, it, expect, vi } from 'vitest'
import { createRouter, createMemoryHistory } from 'vue-router'
import MissionCard from '../MissionCard.vue'

// Router minimal pour résoudre useRouter()
const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/', component: { template: '<div/>' } },
    { path: '/missions/:id', name: 'mission-detail', component: { template: '<div/>' } }
  ]
})

const baseMission = {
  id: 42,
  title: 'Mission Java FinTech',
  description: 'Développement d\'une application bancaire haute performance.'
}

describe('MissionCard.vue', () => {
  it('doit afficher le titre et l\'id de la mission', () => {
    const wrapper = mount(MissionCard, {
      props: { mission: baseMission },
      global: { plugins: [router] }
    })
    expect(wrapper.text()).toContain('Mission Java FinTech')
    expect(wrapper.text()).toContain('#42')
  })

  it('doit afficher le badge de statut DRAFT correctement', () => {
    const wrapper = mount(MissionCard, {
      props: { mission: { ...baseMission, status: 'DRAFT' } },
      global: { plugins: [router] }
    })
    expect(wrapper.text()).toContain('Brouillon')
    expect(wrapper.find('.mc-status-draft').exists()).toBe(true)
  })

  it('doit afficher le badge WON avec emoji', () => {
    const wrapper = mount(MissionCard, {
      props: { mission: { ...baseMission, status: 'WON' } },
      global: { plugins: [router] }
    })
    expect(wrapper.text()).toContain('Gagné')
    expect(wrapper.find('.mc-status-won').exists()).toBe(true)
  })

  it('doit afficher le statut par défaut (STAFFED) si statut absent', () => {
    const wrapper = mount(MissionCard, {
      props: { mission: baseMission }, // pas de status
      global: { plugins: [router] }
    })
    expect(wrapper.text()).toContain('Équipe proposée')
    expect(wrapper.find('.mc-status-staffed').exists()).toBe(true)
  })

  it('doit afficher les compétences extraites si présentes', () => {
    const wrapper = mount(MissionCard, {
      props: { mission: { ...baseMission, extracted_competencies: ['Java', 'Spring Boot', 'Kafka'] } },
      global: { plugins: [router] }
    })
    expect(wrapper.text()).toContain('Java')
    expect(wrapper.text()).toContain('Spring Boot')
    expect(wrapper.findAll('.comp-tag')).toHaveLength(3)
  })

  it('ne doit pas afficher la section compétences si vide', () => {
    const wrapper = mount(MissionCard, {
      props: { mission: { ...baseMission, extracted_competencies: [] } },
      global: { plugins: [router] }
    })
    expect(wrapper.find('.competencies').exists()).toBe(false)
  })

  it('doit afficher les avatars d\'équipe si proposed_team présent', () => {
    const wrapper = mount(MissionCard, {
      props: { mission: { ...baseMission, proposed_team: [
        { full_name: 'Alice Martin' },
        { full_name: 'Bob Dupont' }
      ]}}  ,
      global: { plugins: [router] }
    })
    expect(wrapper.text()).toContain('2 experts suggérés')
    expect(wrapper.findAll('.mini-avatar')).toHaveLength(2)
  })

  it('doit afficher "+N" si l\'équipe dépasse 3 membres', () => {
    const wrapper = mount(MissionCard, {
      props: { mission: { ...baseMission, proposed_team: [
        { full_name: 'Alice Martin' },
        { full_name: 'Bob Dupont' },
        { full_name: 'Claire Petit' },
        { full_name: 'David Leroy' }
      ]}}  ,
      global: { plugins: [router] }
    })
    expect(wrapper.find('.more-members').text()).toBe('+1')
  })

  it('doit naviguer vers la mission au clic', async () => {
    const pushSpy = vi.spyOn(router, 'push')
    const wrapper = mount(MissionCard, {
      props: { mission: baseMission },
      global: { plugins: [router] }
    })
    await wrapper.find('.mission-card').trigger('click')
    expect(pushSpy).toHaveBeenCalledWith({ name: 'mission-detail', params: { id: '42' } })
  })
})
