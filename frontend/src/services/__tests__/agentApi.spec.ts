import { describe, it, expect, vi, beforeEach } from 'vitest'
import axios from 'axios'
import { agentApi } from '../agentApi'

vi.mock('axios', () => ({
  default: {
    post: vi.fn(),
    get: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
    defaults: { headers: { common: {} } },
  },
}))

// ── Mock localStorage ───────────────────────────────────────────────────────
let store: Record<string, string> = {}
Object.defineProperty(global, 'localStorage', {
  value: {
    getItem: (k: string) => store[k] || null,
    setItem: (k: string, v: string) => { store[k] = v },
    removeItem: (k: string) => { delete store[k] },
    clear: () => { store = {} },
  },
  configurable: true,
})

// ── Helpers ─────────────────────────────────────────────────────────────────
function withToken() {
  store['access_token'] = 'test-jwt-token'
}

describe('agentApi', () => {
  beforeEach(() => {
    store = {}
    vi.clearAllMocks()
  })

  // ── query ─────────────────────────────────────────────────────────────────

  describe('query()', () => {
    it('doit faire un POST /api/query sans session_id si absent', async () => {
      const mockData = { response: 'Réponse', steps: [] }
      ;(axios.post as any).mockResolvedValueOnce({ data: mockData })

      const result = await agentApi.query('Liste les missions')

      expect(axios.post).toHaveBeenCalledWith(
        '/api/query',
        { query: 'Liste les missions' },
        { headers: expect.objectContaining({ 'X-Preferred-Language': expect.any(String) }) }
      )
      expect(result).toEqual(mockData)
    })

    it('doit inclure session_id dans le body si fourni', async () => {
      ;(axios.post as any).mockResolvedValueOnce({ data: { response: 'ok' } })

      await agentApi.query('Test', 'u@t.com:abc123')

      const [, body] = (axios.post as any).mock.calls[0]
      expect(body).toEqual({ query: 'Test', session_id: 'u@t.com:abc123' })
    })

    it('doit inclure Authorization si token présent', async () => {
      withToken()
      ;(axios.post as any).mockResolvedValueOnce({ data: { response: 'ok' } })

      await agentApi.query('Test')

      const [, , { headers }] = (axios.post as any).mock.calls[0]
      expect(headers['Authorization']).toBe('Bearer test-jwt-token')
    })

    it('ne doit pas inclure Authorization si token absent', async () => {
      ;(axios.post as any).mockResolvedValueOnce({ data: { response: 'ok' } })

      await agentApi.query('Test')

      const [, , { headers }] = (axios.post as any).mock.calls[0]
      expect(headers['Authorization']).toBeUndefined()
    })
  })

  // ── history ───────────────────────────────────────────────────────────────

  describe('history()', () => {
    it('doit faire un GET /api/history sans params si sessionId absent', async () => {
      ;(axios.get as any).mockResolvedValueOnce({ data: { history: [] } })

      await agentApi.history()

      expect(axios.get).toHaveBeenCalledWith('/api/history', {
        headers: {},
        params: {},
      })
    })

    it('doit passer session_id en query param si fourni', async () => {
      ;(axios.get as any).mockResolvedValueOnce({ data: { history: [] } })

      await agentApi.history('u@t.com:xyz')

      const [, { params }] = (axios.get as any).mock.calls[0]
      expect(params).toEqual({ session_id: 'u@t.com:xyz' })
    })
  })

  // ── resetHistory ──────────────────────────────────────────────────────────

  describe('resetHistory()', () => {
    it('doit faire un DELETE /api/history sans session_id si absent', async () => {
      withToken()
      ;(axios.delete as any).mockResolvedValueOnce({})

      await agentApi.resetHistory()

      expect(axios.delete).toHaveBeenCalledWith('/api/history', {
        headers: { Authorization: 'Bearer test-jwt-token' },
        params: {},
      })
    })

    it('doit passer session_id en query param si fourni', async () => {
      withToken()
      ;(axios.delete as any).mockResolvedValueOnce({})

      await agentApi.resetHistory('u@t.com:abc')

      const [, { params }] = (axios.delete as any).mock.calls[0]
      expect(params).toEqual({ session_id: 'u@t.com:abc' })
    })
  })

  // ── listSessions ──────────────────────────────────────────────────────────

  describe('listSessions()', () => {
    it('doit faire un GET /api/sessions', async () => {
      const mockSessions = { sessions: [{ id: 'u@t.com', name: 'Défaut', created_at: '2026-01-01' }] }
      ;(axios.get as any).mockResolvedValueOnce({ data: mockSessions })

      const result = await agentApi.listSessions()

      expect(axios.get).toHaveBeenCalledWith('/api/sessions', { headers: {} })
      expect(result).toEqual(mockSessions)
    })

    it('doit inclure Authorization si token présent', async () => {
      withToken()
      ;(axios.get as any).mockResolvedValueOnce({ data: { sessions: [] } })

      await agentApi.listSessions()

      const [, { headers }] = (axios.get as any).mock.calls[0]
      expect(headers['Authorization']).toBe('Bearer test-jwt-token')
    })
  })

  // ── createSession ─────────────────────────────────────────────────────────

  describe('createSession()', () => {
    it('doit faire un POST /api/sessions avec le nom', async () => {
      const newSession = { id: 'u@t.com:abc', name: 'Mission Alpha', created_at: '2026-01-01' }
      ;(axios.post as any).mockResolvedValueOnce({ data: newSession })

      const result = await agentApi.createSession('Mission Alpha')

      expect(axios.post).toHaveBeenCalledWith(
        '/api/sessions',
        { name: 'Mission Alpha' },
        { headers: {} }
      )
      expect(result).toEqual(newSession)
    })

    it('doit utiliser "Nouvelle session" si nom non fourni', async () => {
      ;(axios.post as any).mockResolvedValueOnce({ data: { id: 'u:1', name: 'Nouvelle session' } })

      await agentApi.createSession()

      const [, body] = (axios.post as any).mock.calls[0]
      expect(body).toEqual({ name: 'Nouvelle session' })
    })
  })

  // ── renameSession ─────────────────────────────────────────────────────────

  describe('renameSession()', () => {
    it('doit faire un PATCH /api/sessions/{id}', async () => {
      ;(axios.patch as any).mockResolvedValueOnce({ data: { success: true } })

      await agentApi.renameSession('u@t.com:abc', 'Nouveau nom')

      expect(axios.patch).toHaveBeenCalledWith(
        '/api/sessions/u%40t.com%3Aabc',
        { name: 'Nouveau nom' },
        { headers: {} }
      )
    })
  })

  // ── deleteSession ─────────────────────────────────────────────────────────

  describe('deleteSession()', () => {
    it('doit faire un DELETE /api/sessions/{id}', async () => {
      withToken()
      ;(axios.delete as any).mockResolvedValueOnce({ data: { success: true } })

      await agentApi.deleteSession('u@t.com:abc')

      expect(axios.delete).toHaveBeenCalledWith(
        '/api/sessions/u%40t.com%3Aabc',
        { headers: { Authorization: 'Bearer test-jwt-token' } }
      )
    })
  })
})
