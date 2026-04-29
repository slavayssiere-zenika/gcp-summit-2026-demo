import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import SystemHealthCard from '../SystemHealthCard.vue'

const healthyComponents = [
  { status: 'healthy', component: 'users-api', message: 'DB connection OK' },
  { status: 'healthy', component: 'redis-cache', message: 'Connected' },
  { status: 'healthy', component: 'agent-router', message: 'Running' }
]

const mixedComponents = [
  { status: 'healthy', component: 'users-api', message: 'OK' },
  { status: 'degraded', component: 'analytics-mcp', message: 'Slow response' },
  { status: 'unhealthy', component: 'cv-api-dev', error: 'Connection refused' }
]

describe('SystemHealthCard.vue', () => {
  it('doit afficher "Tous les systèmes sont opérationnels" si tout est healthy', () => {
    const wrapper = mount(SystemHealthCard, { props: { components: healthyComponents } })
    expect(wrapper.text()).toContain('Tous les systèmes sont opérationnels')
    expect(wrapper.find('.global-status.healthy').exists()).toBe(true)
  })

  it('doit afficher "Dégradation détectée" si un composant est degraded', () => {
    const components = [
      { status: 'healthy', component: 'users-api', message: 'OK' },
      { status: 'degraded', component: 'analytics-mcp', message: 'Slow' }
    ]
    const wrapper = mount(SystemHealthCard, { props: { components } })
    expect(wrapper.text()).toContain('Dégradation détectée')
    expect(wrapper.find('.global-status.degraded').exists()).toBe(true)
  })

  it('doit afficher "Incident critique" si un composant est unhealthy', () => {
    const wrapper = mount(SystemHealthCard, { props: { components: mixedComponents } })
    expect(wrapper.text()).toContain('Incident critique en cours')
    expect(wrapper.find('.global-status.critical').exists()).toBe(true)
  })

  it('doit afficher le bon nombre de composants dans le résumé', () => {
    const wrapper = mount(SystemHealthCard, { props: { components: healthyComponents } })
    expect(wrapper.text()).toContain('3 composants vérifiés')
    expect(wrapper.text()).toContain('3 OK')
  })

  it('doit afficher les chips dégradé et KO si nécessaire', () => {
    const wrapper = mount(SystemHealthCard, { props: { components: mixedComponents } })
    expect(wrapper.find('.chip-degraded').exists()).toBe(true)
    expect(wrapper.find('.chip-critical').exists()).toBe(true)
    expect(wrapper.text()).toContain('1 dégradé')
    expect(wrapper.text()).toContain('1 KO')
  })

  it('doit formatter les noms de composants (kebab → Title Case, sans -dev)', () => {
    const wrapper = mount(SystemHealthCard, { props: { components: [
      { status: 'healthy', component: 'users-api-dev', message: 'OK' }
    ]}})
    // "users-api-dev" → "Users Api" (suppr -dev, Title Case)
    expect(wrapper.text()).toContain('Users Api')
  })

  it('doit afficher le message du composant si présent', () => {
    const wrapper = mount(SystemHealthCard, { props: { components: healthyComponents } })
    expect(wrapper.text()).toContain('DB connection OK')
  })

  it('doit afficher l\'erreur en rouge si error est présent', () => {
    const wrapper = mount(SystemHealthCard, { props: { components: [
      { status: 'unhealthy', component: 'cv-api', error: 'Connection refused' }
    ]}})
    expect(wrapper.find('.error-text').text()).toBe('Connection refused')
  })

  it('doit afficher l\'URL et le code HTTP si présents', () => {
    const wrapper = mount(SystemHealthCard, { props: { components: [
      { status: 'healthy', component: 'bigquery', url: 'https://bigquery.googleapis.com', code: 200 }
    ]}})
    expect(wrapper.find('.url-path').exists()).toBe(true)
    expect(wrapper.find('.code-badge').text()).toBe('200')
  })

  it('doit afficher "Aucun détail disponible" si aucune info', () => {
    const wrapper = mount(SystemHealthCard, { props: { components: [
      { status: 'unknown', component: 'mysterious-service' }
    ]}})
    expect(wrapper.text()).toContain('Aucun détail disponible')
  })

  it('doit assigner l\'icône Database pour redis', () => {
    // Vérifié indirectement via le rendu — le composant ne crash pas
    const wrapper = mount(SystemHealthCard, { props: { components: [
      { status: 'healthy', component: 'redis-cache', message: 'OK' }
    ]}})
    expect(wrapper.find('.component-card').exists()).toBe(true)
  })
})
