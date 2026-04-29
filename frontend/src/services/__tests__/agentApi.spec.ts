import { describe, it, expect, vi, beforeEach } from 'vitest'
import axios from 'axios'
import { agentApi } from '../agentApi'

vi.mock('axios', () => ({
  default: {
    post: vi.fn(),
    get: vi.fn(),
    delete: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() }
    },
    defaults: { headers: { common: {} } }
  }
}))

// Mock localStorage
let store: Record<string, string> = {}
Object.defineProperty(global, 'localStorage', {
  value: {
    getItem: (k: string) => store[k] || null,
    setItem: (k: string, v: string) => { store[k] = v },
    removeItem: (k: string) => { delete store[k] },
    clear: () => { store = {} }
  }
})

describe('agentApi', () => {
  beforeEach(() => {
    store = {}
    vi.clearAllMocks()
  })

  it('query doit faire un POST /api/query et retourner les données', async () => {
    const mockData = { response: 'Voici les missions', steps: [] }
    ;(axios.post as any).mockResolvedValueOnce({ data: mockData })

    const result = await agentApi.query('Liste les missions')

    expect(axios.post).toHaveBeenCalledWith('/api/query', { query: 'Liste les missions' })
    expect(result).toEqual(mockData)
  })

  it('history doit faire un GET /api/history et retourner l\'historique', async () => {
    const mockHistory = { history: [{ role: 'user', content: 'Hello' }] }
    ;(axios.get as any).mockResolvedValueOnce({ data: mockHistory })

    const result = await agentApi.history()

    expect(axios.get).toHaveBeenCalledWith('/api/history')
    expect(result).toEqual(mockHistory)
  })

  it('resetHistory doit faire un DELETE /api/history avec token si présent', async () => {
    store['access_token'] = 'mon-token-secret'
    ;(axios.delete as any).mockResolvedValueOnce({})

    await agentApi.resetHistory()

    expect(axios.delete).toHaveBeenCalledWith('/api/history', {
      headers: { Authorization: 'Bearer mon-token-secret' }
    })
  })

  it('resetHistory doit faire un DELETE sans Authorization si token absent', async () => {
    ;(axios.delete as any).mockResolvedValueOnce({})

    await agentApi.resetHistory()

    expect(axios.delete).toHaveBeenCalledWith('/api/history', { headers: {} })
  })
})
