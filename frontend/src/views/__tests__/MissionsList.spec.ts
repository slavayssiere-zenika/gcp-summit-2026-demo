import { mount, flushPromises } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createRouter, createMemoryHistory } from 'vue-router'
import axios from 'axios'
import MissionsList from '../MissionsList.vue'

vi.mock('axios')
vi.mock('@vueuse/head', () => ({ useHead: vi.fn() }))

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/', component: { template: '<div/>' } },
    { path: '/missions', component: MissionsList },
    { path: '/missions/:id', name: 'mission-detail', component: { template: '<div/>' } },
    { path: '/missions/new', name: 'mission-new', component: { template: '<div/>' } }
  ]
})

const fakeMissions = [
  { id: 1, title: 'Mission Java', description: 'Description de la mission Java FinTech', status: 'STAFFED', extracted_competencies: ['Java', 'Spring'], proposed_team: [{ user_id: 10 }] },
  { id: 2, title: 'Mission Python', description: 'Description de la mission Python Data', status: 'WON', extracted_competencies: [], proposed_team: [] },
  { id: 3, title: 'Mission React', description: 'Description de la mission React Frontend', status: 'DRAFT', extracted_competencies: [], proposed_team: [] },
]

describe('MissionsList.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('doit afficher l\'état de chargement initialement', () => {
    ;(axios.get as any).mockReturnValue(new Promise(() => {})) // never resolves
    const wrapper = mount(MissionsList, { global: { plugins: [router] } })
    expect(wrapper.find('.loading-state').exists()).toBe(true)
  })

  it('doit afficher la liste des missions après chargement', async () => {
    ;(axios.get as any).mockResolvedValueOnce({ data: fakeMissions })
    const wrapper = mount(MissionsList, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.find('.loading-state').exists()).toBe(false)
    expect(wrapper.findAll('.mission-card')).toHaveLength(3)
    expect(wrapper.text()).toContain('Mission Java')
    expect(wrapper.text()).toContain('Mission Python')
  })

  it('doit afficher l\'état vide si aucune mission', async () => {
    ;(axios.get as any).mockResolvedValueOnce({ data: [] })
    const wrapper = mount(MissionsList, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.find('.empty-state').exists()).toBe(true)
    expect(wrapper.text()).toContain('Aucune mission')
  })

  it('doit filtrer par statut au clic sur un onglet', async () => {
    ;(axios.get as any).mockResolvedValueOnce({ data: fakeMissions })
    const wrapper = mount(MissionsList, { global: { plugins: [router] } })
    await flushPromises()

    // 3 missions visibles initialement (filtre ALL)
    expect(wrapper.findAll('.mission-card')).toHaveLength(3)

    // Clic sur l'onglet STAFFED
    const tabs = wrapper.findAll('.filter-tab')
    const staffedTab = tabs.find(t => t.text().includes('Équipe proposée'))
    await staffedTab!.trigger('click')

    expect(wrapper.findAll('.mission-card')).toHaveLength(1)
    expect(wrapper.text()).toContain('Mission Java')
  })

  it('doit afficher un message si aucune mission pour le filtre sélectionné', async () => {
    ;(axios.get as any).mockResolvedValueOnce({ data: fakeMissions })
    const wrapper = mount(MissionsList, { global: { plugins: [router] } })
    await flushPromises()

    // Clic sur NO_GO — aucune mission n'a ce statut
    const tabs = wrapper.findAll('.filter-tab')
    const nogoTab = tabs.find(t => t.text().includes('No-Go'))
    await nogoTab!.trigger('click')

    expect(wrapper.find('.empty-filtered').exists()).toBe(true)
  })

  it('doit naviguer vers la mission au clic sur une card', async () => {
    ;(axios.get as any).mockResolvedValueOnce({ data: fakeMissions })
    const pushSpy = vi.spyOn(router, 'push')
    const wrapper = mount(MissionsList, { global: { plugins: [router] } })
    await flushPromises()

    await wrapper.findAll('.mission-card')[0].trigger('click')
    expect(pushSpy).toHaveBeenCalledWith('/missions/1')
  })

  it('doit naviguer vers /missions/new au clic sur Nouvelle Mission', async () => {
    ;(axios.get as any).mockResolvedValueOnce({ data: fakeMissions })
    const pushSpy = vi.spyOn(router, 'push')
    const wrapper = mount(MissionsList, { global: { plugins: [router] } })
    await flushPromises()

    await wrapper.find('.action-btn').trigger('click')
    expect(pushSpy).toHaveBeenCalledWith('/missions/new')
  })

  it('doit afficher les skills (max 3 + badge +N)', async () => {
    const missions = [{ id: 1, title: 'Full Stack', description: 'Desc', status: 'STAFFED',
      extracted_competencies: ['Java', 'Python', 'React', 'Docker'], proposed_team: [] }]
    ;(axios.get as any).mockResolvedValueOnce({ data: missions })
    const wrapper = mount(MissionsList, { global: { plugins: [router] } })
    await flushPromises()

    const tags = wrapper.findAll('.skill-tag')
    // 3 tags normaux + 1 badge "+1"
    expect(tags).toHaveLength(4)
    expect(wrapper.find('.skill-tag.extra').text()).toBe('+1')
  })
})
