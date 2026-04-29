import { mount, flushPromises } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createRouter, createMemoryHistory } from 'vue-router'
import Login from '../Login.vue'

// Mock authService
vi.mock('../../services/auth', () => ({
  authService: {
    state: { isAuthenticated: false },
    checkAuth: vi.fn().mockResolvedValue(undefined),
    login: vi.fn()
  }
}))

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/', component: { template: '<div>Home</div>' } },
    { path: '/login', component: Login }
  ]
})

describe('Login.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('doit afficher le titre et le formulaire', async () => {
    const wrapper = mount(Login, {
      global: { plugins: [router] }
    })
    await flushPromises()
    expect(wrapper.text()).toContain('Console Agent')
    expect(wrapper.find('input[type="email"]').exists()).toBe(true)
    expect(wrapper.find('input[type="password"]').exists()).toBe(true)
  })

  it('doit afficher une erreur si les champs sont vides', async () => {
    const wrapper = mount(Login, {
      global: { plugins: [router] }
    })
    await flushPromises()

    await wrapper.find('form').trigger('submit')

    expect(wrapper.text()).toContain('Veuillez remplir tous les champs')
    expect(wrapper.find('.error-banner').exists()).toBe(true)
  })

  it('doit appeler authService.login avec email et password', async () => {
    const { authService } = await import('../../services/auth')
    ;(authService.login as any).mockResolvedValueOnce({})

    const wrapper = mount(Login, {
      global: { plugins: [router] }
    })
    await flushPromises()

    await wrapper.find('input[type="email"]').setValue('admin@zenika.com')
    await wrapper.find('input[type="password"]').setValue('secretpassword')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(authService.login).toHaveBeenCalledWith('admin@zenika.com', 'secretpassword')
  })

  it('doit afficher un message d\'erreur si le login échoue', async () => {
    const { authService } = await import('../../services/auth')
    ;(authService.login as any).mockRejectedValueOnce('Identifiants invalides')

    const wrapper = mount(Login, {
      global: { plugins: [router] }
    })
    await flushPromises()

    await wrapper.find('input[type="email"]').setValue('bad@zenika.com')
    await wrapper.find('input[type="password"]').setValue('wrongpass')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(wrapper.find('.error-banner').exists()).toBe(true)
    expect(wrapper.text()).toContain('Identifiants invalides')
  })
})
