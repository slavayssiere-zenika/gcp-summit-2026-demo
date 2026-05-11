import { mount, flushPromises } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createRouter, createMemoryHistory } from 'vue-router'
import axios from 'axios'
import Competencies from '../Competencies.vue'

// Mock axios
vi.mock('axios', () => {
  return {
    default: {
      get: vi.fn(),
      post: vi.fn()
    }
  }
})

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/', component: { template: '<div>Home</div>' } },
    { path: '/user/:id', name: 'user-detail', component: { template: '<div>User Detail</div>' } }
  ]
})

describe('Competencies.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('doit envoyer le bon format { user_ids: [...] } pour la requête bulk lors de la sélection d\'une compétence', async () => {
    // 1. Initial fetch mock for root competencies
    ;(axios.get as any).mockResolvedValueOnce({
      data: {
        items: [{ id: 1, name: 'Vert.x', sub_competencies: [] }],
        total: 1
      }
    })

    const wrapper = mount(Competencies, {
      global: { plugins: [router] }
    })
    
    await flushPromises()

    const node = wrapper.findComponent({ name: 'CompetencyNode' })
    expect(node.exists()).toBe(true)

    // Mock responses for selecting a leaf
    // 1. GET /api/competencies/1/users
    ;(axios.get as any).mockResolvedValueOnce({
      data: [101, 102, 103] // 3 users
    })

    // 2. POST /api/users/bulk
    ;(axios.post as any).mockResolvedValueOnce({
      data: [
        { id: 101, full_name: 'John Doe', email: 'john@example.com', role: 'consultant' },
        { id: 102, full_name: 'Jane Smith', email: 'jane@example.com', role: 'consultant' },
        { id: 103, full_name: 'Bob Bob', email: 'bob@example.com', role: 'consultant' }
      ]
    })

    // 3. POST /api/competencies/evaluations/batch/users
    ;(axios.post as any).mockResolvedValueOnce({
      data: {
        evaluations: {
          '101': { user_id: 101, ai_score: 4 },
          '102': { user_id: 102, ai_score: 3 },
          '103': { user_id: 103, ai_score: 5 }
        }
      }
    })

    await node.vm.$emit('select-leaf', { id: 1, name: 'Vert.x' })
    await flushPromises()

    // Vérification stricte du payload
    expect(axios.post).toHaveBeenNthCalledWith(1, '/api/users/bulk', { user_ids: [101, 102, 103] })
    expect(axios.post).toHaveBeenNthCalledWith(2, '/api/competencies/evaluations/batch/users', {
      competency_id: 1,
      user_ids: [101, 102, 103]
    })
    
    // Vérification de l'interface
    expect(wrapper.text()).toContain('John Doe')
    expect(wrapper.text()).toContain('Jane Smith')
    expect(wrapper.text()).toContain('3 consultant(s)')
  })
})
