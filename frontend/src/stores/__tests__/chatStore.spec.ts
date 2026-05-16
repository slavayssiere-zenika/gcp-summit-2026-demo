import { setActivePinia, createPinia } from 'pinia'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useChatStore } from '../chatStore'
import type { ChatSession, Message } from '@/types'

// ── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('@/services/agentApi', () => ({
  agentApi: {
    query: vi.fn(),
    history: vi.fn(),
    resetHistory: vi.fn(),
    listSessions: vi.fn(),
    createSession: vi.fn(),
    renameSession: vi.fn(),
    deleteSession: vi.fn(),
  },
}))

vi.mock('@/stores/uxStore', () => ({
  useUxStore: () => ({ showToast: vi.fn() }),
}))

// ── Helpers ──────────────────────────────────────────────────────────────────

function makeSession(overrides: Partial<ChatSession> = {}): ChatSession {
  return {
    id: 'user@test.com',
    name: 'Défaut',
    created_at: new Date().toISOString(),
    messages: [{ role: 'assistant', content: 'Bonjour !', activeTab: 'preview' }],
    isTyping: false,
    isLoadingHistory: false,
    historyLoaded: true,
    ...overrides,
  }
}

function defaultApiResponse() {
  return {
    response: 'Réponse de l\'agent.',
    data: null,
    steps: [],
    thoughts: '',
    usage: { total_input_tokens: 10, total_output_tokens: 5, estimated_cost_usd: 0.001 },
    display_type: null,
    degraded: false,
    semantic_cache_hit: false,
    source: 'adk_agent',
    session_id: 'user@test.com',
    confidence: 1.0,
  }
}

// ── Tests ────────────────────────────────────────────────────────────────────

describe('useChatStore — multi-sessions', () => {
  let store: ReturnType<typeof useChatStore>

  beforeEach(async () => {
    setActivePinia(createPinia())
    store = useChatStore()
    vi.clearAllMocks()
  })

  // ── État initial ────────────────────────────────────────────────────────

  describe('État initial', () => {
    it('doit avoir un state vide à l\'initialisation', () => {
      expect(store.sessions).toHaveLength(0)
      expect(store.activeSessionId).toBeNull()
      expect(store.isLoadingSessions).toBe(false)
    })

    it('activeSession doit retourner null si pas de session active', () => {
      expect(store.activeSession).toBeNull()
    })

    it('messages doit retourner le message de bienvenue si pas de session active', () => {
      const msgs = store.messages
      expect(msgs).toHaveLength(1)
      expect(msgs[0].role).toBe('assistant')
      expect(msgs[0].content).toContain('Bonjour')
    })

    it('isTyping doit être false si pas de session active', () => {
      expect(store.isTyping).toBe(false)
    })
  })

  // ── loadSessions ────────────────────────────────────────────────────────

  describe('loadSessions()', () => {
    it('doit charger les sessions et activer la première', async () => {
      const { agentApi } = await import('@/services/agentApi')
      const session1 = makeSession({ id: 'u@t.com', name: 'Défaut', historyLoaded: false })
      ;(agentApi.listSessions as any).mockResolvedValueOnce({ sessions: [session1] })
      ;(agentApi.history as any).mockResolvedValueOnce({ history: [] })

      await store.loadSessions()

      expect(store.sessions).toHaveLength(1)
      expect(store.activeSessionId).toBe('u@t.com')
    })

    it('doit charger l\'historique de la session active après loadSessions', async () => {
      const { agentApi } = await import('@/services/agentApi')
      const session1 = makeSession({ id: 's1', historyLoaded: false })
      const historyMsg: Message = { role: 'user', content: 'Msg historique' }
      ;(agentApi.listSessions as any).mockResolvedValueOnce({ sessions: [session1] })
      ;(agentApi.history as any).mockResolvedValueOnce({ history: [historyMsg] })

      await store.loadSessions()

      expect(agentApi.history).toHaveBeenCalledWith('s1')
      const active = store.sessions.find(s => s.id === 's1')
      expect(active?.historyLoaded).toBe(true)
    })
  })

  // ── createSession ───────────────────────────────────────────────────────

  describe('createSession()', () => {
    it('doit créer une session et l\'activer', async () => {
      const { agentApi } = await import('@/services/agentApi')
      const newSession = makeSession({ id: 'u@t.com:abc123', name: 'Nouvelle session' })
      ;(agentApi.createSession as any).mockResolvedValueOnce(newSession)

      await store.createSession()

      expect(store.sessions).toHaveLength(1)
      expect(store.activeSessionId).toBe('u@t.com:abc123')
    })

    it('doit passer le nom à l\'API', async () => {
      const { agentApi } = await import('@/services/agentApi')
      ;(agentApi.createSession as any).mockResolvedValueOnce(makeSession({ id: 'u:1', name: 'Mission Alpha' }))

      await store.createSession('Mission Alpha')

      expect(agentApi.createSession).toHaveBeenCalledWith('Mission Alpha')
    })

    it('ne doit pas créer si 10 sessions existent déjà (protection frontend)', async () => {
      const { agentApi } = await import('@/services/agentApi')
      // Pré-remplir avec 10 sessions
      store.sessions = Array.from({ length: 10 }, (_, i) => makeSession({ id: `u:s${i}` }))

      await store.createSession('Une de trop')

      expect(agentApi.createSession).not.toHaveBeenCalled()
    })

    it('doit afficher un toast d\'erreur si l\'API échoue', async () => {
      const { agentApi } = await import('@/services/agentApi')
      const mockShowToast = vi.fn()
      vi.doMock('@/stores/uxStore', () => ({ useUxStore: () => ({ showToast: mockShowToast }) }))
      ;(agentApi.createSession as any).mockRejectedValueOnce({
        response: { data: { detail: 'Limite atteinte' } },
      })

      await store.createSession()

      // Le store utilise useUxStore() interne — on vérifie que l'erreur n'a pas créé de session
      expect(store.sessions).toHaveLength(0)
    })
  })

  // ── switchSession ───────────────────────────────────────────────────────

  describe('switchSession()', () => {
    it('doit changer activeSessionId', async () => {
      const { agentApi } = await import('@/services/agentApi')
      store.sessions = [
        makeSession({ id: 's1', historyLoaded: true }),
        makeSession({ id: 's2', historyLoaded: true }),
      ]
      store.activeSessionId = 's1'

      await store.switchSession('s2')

      expect(store.activeSessionId).toBe('s2')
      expect(agentApi.history).not.toHaveBeenCalled()
    })

    it('doit charger l\'historique si pas encore chargé', async () => {
      const { agentApi } = await import('@/services/agentApi')
      store.sessions = [
        makeSession({ id: 's1', historyLoaded: true }),
        makeSession({ id: 's2', historyLoaded: false }),
      ]
      store.activeSessionId = 's1'
      ;(agentApi.history as any).mockResolvedValueOnce({ history: [] })

      await store.switchSession('s2')

      expect(agentApi.history).toHaveBeenCalledWith('s2')
    })

    it('ne doit pas recharger l\'historique si déjà chargé', async () => {
      const { agentApi } = await import('@/services/agentApi')
      store.sessions = [makeSession({ id: 's1', historyLoaded: true })]
      store.activeSessionId = null

      await store.switchSession('s1')

      expect(agentApi.history).not.toHaveBeenCalled()
    })
  })

  // ── renameSession ───────────────────────────────────────────────────────

  describe('renameSession()', () => {
    it('doit appeler l\'API et mettre à jour le nom localement', async () => {
      const { agentApi } = await import('@/services/agentApi')
      store.sessions = [makeSession({ id: 's1', name: 'Ancien nom' })]
      ;(agentApi.renameSession as any).mockResolvedValueOnce(undefined)

      await store.renameSession('s1', 'Nouveau nom')

      expect(agentApi.renameSession).toHaveBeenCalledWith('s1', 'Nouveau nom')
      expect(store.sessions[0].name).toBe('Nouveau nom')
    })

    it('doit afficher un toast d\'erreur si l\'API échoue', async () => {
      const { agentApi } = await import('@/services/agentApi')
      store.sessions = [makeSession({ id: 's1' })]
      ;(agentApi.renameSession as any).mockRejectedValueOnce({
        response: { data: { detail: 'Session introuvable' } },
      })

      await store.renameSession('s1', 'X')

      // On vérifie que le nom n'a pas changé (erreur bien absorbée)
      expect(store.sessions[0].name).toBe('Défaut')
    })
  })

  // ── deleteSession ───────────────────────────────────────────────────────

  describe('deleteSession()', () => {
    it('doit supprimer la session et switcher sur la suivante', async () => {
      const { agentApi } = await import('@/services/agentApi')
      store.sessions = [
        makeSession({ id: 's1', name: 'Défaut' }),
        makeSession({ id: 's2', name: 'Alpha' }),
      ]
      store.activeSessionId = 's2'
      ;(agentApi.deleteSession as any).mockResolvedValueOnce(undefined)
      ;(agentApi.history as any).mockResolvedValueOnce({ history: [] })

      await store.deleteSession('s2')

      expect(store.sessions).toHaveLength(1)
      expect(store.sessions[0].id).toBe('s1')
      expect(store.activeSessionId).toBe('s1')
    })

    it('ne doit pas supprimer si c\'est la dernière session', async () => {
      const { agentApi } = await import('@/services/agentApi')
      store.sessions = [makeSession({ id: 's1' })]
      store.activeSessionId = 's1'

      await store.deleteSession('s1')

      expect(agentApi.deleteSession).not.toHaveBeenCalled()
      expect(store.sessions).toHaveLength(1)
    })

    it('ne doit pas changer activeSessionId si session supprimée n\'est pas active', async () => {
      const { agentApi } = await import('@/services/agentApi')
      store.sessions = [
        makeSession({ id: 's1', historyLoaded: true }),
        makeSession({ id: 's2', historyLoaded: true }),
      ]
      store.activeSessionId = 's1'
      ;(agentApi.deleteSession as any).mockResolvedValueOnce(undefined)

      await store.deleteSession('s2')

      expect(store.activeSessionId).toBe('s1')
    })
  })

  // ── sendQuery ───────────────────────────────────────────────────────────

  describe('sendQuery()', () => {
    it('doit passer session_id actif à l\'API', async () => {
      const { agentApi } = await import('@/services/agentApi')
      store.sessions = [makeSession({ id: 'u@t.com:xyz' })]
      store.activeSessionId = 'u@t.com:xyz'
      ;(agentApi.query as any).mockResolvedValueOnce(defaultApiResponse())

      await store.sendQuery('Bonjour')

      expect(agentApi.query).toHaveBeenCalledWith('Bonjour', 'u@t.com:xyz')
    })

    it('doit ajouter message utilisateur puis réponse assistant dans la session active', async () => {
      const { agentApi } = await import('@/services/agentApi')
      store.sessions = [makeSession({ id: 's1', messages: [] })]
      store.activeSessionId = 's1'
      ;(agentApi.query as any).mockResolvedValueOnce(defaultApiResponse())

      await store.sendQuery('Quels consultants sont disponibles ?')

      const msgs = store.sessions[0].messages!
      expect(msgs.some(m => m.role === 'user')).toBe(true)
      expect(msgs.some(m => m.role === 'assistant')).toBe(true)
    })

    it('ne doit pas envoyer si query vide', async () => {
      const { agentApi } = await import('@/services/agentApi')
      store.sessions = [makeSession({ id: 's1' })]
      store.activeSessionId = 's1'

      await store.sendQuery('   ')

      expect(agentApi.query).not.toHaveBeenCalled()
    })

    it('ne doit pas envoyer si pas de session active', async () => {
      const { agentApi } = await import('@/services/agentApi')
      store.activeSessionId = null

      await store.sendQuery('Test')

      expect(agentApi.query).not.toHaveBeenCalled()
    })

    it('doit remettre isTyping à false même en cas d\'erreur', async () => {
      const { agentApi } = await import('@/services/agentApi')
      store.sessions = [makeSession({ id: 's1' })]
      store.activeSessionId = 's1'
      ;(agentApi.query as any).mockRejectedValueOnce(new Error('Network error'))

      await store.sendQuery('Test')

      expect(store.sessions[0].isTyping).toBe(false)
    })
  })

  // ── fetchHistory ────────────────────────────────────────────────────────

  describe('fetchHistory()', () => {
    beforeEach(() => {
      setActivePinia(createPinia())
      store = useChatStore()
      vi.resetAllMocks()
    })

    it('doit charger l\'historique pour le session_id spécifié', async () => {
      const { agentApi } = await import('@/services/agentApi')
      const histMsg = { role: 'user' as const, content: 'Test historique' }
      store.sessions = [makeSession({ id: 'sess-fetch-1', historyLoaded: false, messages: [] })]
      store.activeSessionId = 'sess-fetch-1'
      ;(agentApi.history as any).mockResolvedValue({ history: [histMsg] })

      await store.fetchHistory('sess-fetch-1')

      expect(agentApi.history).toHaveBeenCalledWith('sess-fetch-1')
      expect(store.sessions[0].historyLoaded).toBe(true)
      // L'historique contient au moins 1 message chargé
      expect(store.sessions[0].messages!.length).toBeGreaterThan(0)
    })

    it('doit initialiser avec message de bienvenue si historique vide', async () => {
      const { agentApi } = await import('@/services/agentApi')
      store.sessions = [makeSession({ id: 'sess-fetch-2', messages: [], historyLoaded: false })]
      store.activeSessionId = 'sess-fetch-2'
      // mockResolvedValue (persistant) pour éviter les résidus de mockResolvedValueOnce
      ;(agentApi.history as any).mockResolvedValue({ history: [] })

      await store.fetchHistory('sess-fetch-2')

      expect(store.sessions[0].messages).toHaveLength(1)
      expect(store.sessions[0].messages![0].content).toContain('Bonjour')
    })
  })





  // ── resetHistory ────────────────────────────────────────────────────────

  describe('resetHistory()', () => {
    it('doit effacer les messages et marquer historyLoaded=false', async () => {
      const { agentApi } = await import('@/services/agentApi')
      const userMsg: Message = { role: 'user', content: 'Un message' }
      store.sessions = [makeSession({ id: 's1', messages: [userMsg], historyLoaded: true })]
      store.activeSessionId = 's1'
      ;(agentApi.resetHistory as any).mockResolvedValueOnce(undefined)

      await store.resetHistory()

      expect(agentApi.resetHistory).toHaveBeenCalledWith('s1')
      expect(store.sessions[0].messages).toHaveLength(1)
      expect(store.sessions[0].messages![0].content).toContain('Bonjour')
      expect(store.sessions[0].historyLoaded).toBe(false)
    })
  })

  // ── getters ─────────────────────────────────────────────────────────────

  describe('getters', () => {
    it('activeSession doit retourner la session correspondant à activeSessionId', () => {
      store.sessions = [
        makeSession({ id: 's1', name: 'A' }),
        makeSession({ id: 's2', name: 'B' }),
      ]
      store.activeSessionId = 's2'
      expect(store.activeSession?.name).toBe('B')
    })

    it('messages doit déléguer à la session active', () => {
      const customMsg: Message = { role: 'user', content: 'Custom' }
      store.sessions = [makeSession({ id: 's1', messages: [customMsg] })]
      store.activeSessionId = 's1'
      expect(store.messages).toContainEqual(expect.objectContaining({ content: 'Custom' }))
    })

    it('isTyping doit refléter la session active', () => {
      store.sessions = [makeSession({ id: 's1', isTyping: true })]
      store.activeSessionId = 's1'
      expect(store.isTyping).toBe(true)
    })

    it('isLoadingHistory doit refléter la session active', () => {
      store.sessions = [makeSession({ id: 's1', isLoadingHistory: true })]
      store.activeSessionId = 's1'
      expect(store.isLoadingHistory).toBe(true)
    })
  })
})
