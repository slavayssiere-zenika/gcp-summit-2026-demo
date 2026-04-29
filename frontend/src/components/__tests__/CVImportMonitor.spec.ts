import { mount } from '@vue/test-utils'
import { describe, it, expect, vi } from 'vitest'
import CVImportMonitor from '../CVImportMonitor.vue'
import axios from 'axios'

// Mocking axios
vi.mock('axios')

// Mocking authService
vi.mock('../../services/auth', () => ({
  authService: {
    state: {
      token: 'fake-token'
    }
  }
}))

describe('CVImportMonitor.vue', () => {
  it('doit s\'afficher correctement en état de chargement initial', () => {
    // Setup axios mock
    (axios.get as any).mockResolvedValue({
      data: {
        pending: 0, queued: 0, processing: 0,
        imported: 10, ignored: 0, errors: 0
      }
    })
    
    const wrapper = mount(CVImportMonitor, {
      global: {
        stubs: {
          RouterLink: true
        }
      }
    })
    
    // Verify it renders
    expect(wrapper.exists()).toBe(true)
    
    // Check loading text initially
    expect(wrapper.text()).toContain('Chargement')
  })
})
