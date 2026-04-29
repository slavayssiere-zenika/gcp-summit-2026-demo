import { setActivePinia, createPinia } from 'pinia'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { extractDebugPrompt, useChatStore } from '../chatStore'

// Mock agentApi
vi.mock('@/services/agentApi', () => ({
  agentApi: {
    query: vi.fn(),
    history: vi.fn(),
    resetHistory: vi.fn()
  }
}))

describe('extractDebugPrompt', () => {
  it('doit extraire un bloc *** ... ***', () => {
    const longContent = 'Voici le prompt suggéré par l\'agent pour vous aider dans votre recherche de consultants disponibles.'
    const markdown = `Voici l'analyse.\n\n***\n${longContent}\n***`
    const result = extractDebugPrompt(markdown)
    expect(result).not.toBeNull()
    expect(result).toContain("prompt suggéré")
  })

  it('doit extraire un bloc ### Prompt', () => {
    const markdown = `Résultat de l'analyse.\n\n### Prompt suggéré\nCeci est un prompt d'au moins 80 caractères pour satisfaire la condition de longueur minimale requise.`
    const result = extractDebugPrompt(markdown)
    expect(result).not.toBeNull()
  })

  it('doit retourner null si pas de debug prompt', () => {
    const markdown = 'Simple réponse texte sans bloc de debug'
    expect(extractDebugPrompt(markdown)).toBeNull()
  })

  it('doit retourner null pour un bloc *** trop court', () => {
    const markdown = '***\nCourt\n***'
    expect(extractDebugPrompt(markdown)).toBeNull()
  })
})

describe('useChatStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('doit avoir un message de bienvenue initial', () => {
    const store = useChatStore()
    expect(store.messages).toHaveLength(1)
    expect(store.messages[0].role).toBe('assistant')
    expect(store.messages[0].content).toContain('Bonjour')
  })

  it('doit ajouter un message utilisateur via addMessage', () => {
    const store = useChatStore()
    store.addMessage({ role: 'user', content: 'Bonjour !' })
    expect(store.messages).toHaveLength(2)
    expect(store.messages[1].role).toBe('user')
    expect(store.messages[1].activeTab).toBe('preview')
  })

  it('doit envoyer une query et ajouter la réponse', async () => {
    const { agentApi } = await import('@/services/agentApi')
    ;(agentApi.query as any).mockResolvedValueOnce({
      response: 'Voici les résultats.',
      data: null,
      steps: [],
      thoughts: '',
      usage: {}
    })

    const store = useChatStore()
    await store.sendQuery('Liste les missions')

    // 1 message initial + 1 user + 1 assistant
    expect(store.messages).toHaveLength(3)
    expect(store.messages[1].role).toBe('user')
    expect(store.messages[2].role).toBe('assistant')
    expect(store.messages[2].content).toBe('Voici les résultats.')
    expect(store.isTyping).toBe(false)
  })

  it('ne doit pas envoyer si la query est vide', async () => {
    const { agentApi } = await import('@/services/agentApi')
    const store = useChatStore()
    await store.sendQuery('   ')
    expect(agentApi.query).not.toHaveBeenCalled()
    expect(store.messages).toHaveLength(1)
  })

  it('doit réinitialiser l\'historique via resetHistory', async () => {
    const { agentApi } = await import('@/services/agentApi')
    ;(agentApi.resetHistory as any).mockResolvedValueOnce({})

    const store = useChatStore()
    store.addMessage({ role: 'user', content: 'Un message' })
    expect(store.messages).toHaveLength(2)

    await store.resetHistory()
    expect(store.messages).toHaveLength(1)
    expect(store.messages[0].content).toContain('Bonjour')
  })
})
