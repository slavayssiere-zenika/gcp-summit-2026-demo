import { defineStore } from 'pinia'
import type { ChatSession, Message } from '@/types'
import { agentApi } from '@/services/agentApi'
import { treeify } from '@/utils/treeify'
import { useUxStore } from './uxStore'

// ── Helpers (repris de l'implémentation précédente) ──────────────────────────

function looksLikeJson(s: string): boolean {
  const trimmed = s.trimStart()
  return trimmed.startsWith('{') || trimmed.startsWith('[')
}

function isNumericKeyMap(obj: any): boolean {
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return false
  const keys = Object.keys(obj)
  if (keys.length < 5) return false
  return keys.every(k => /^\d+$/.test(k))
}

function isCloudRunLogs(data: any[]): boolean {
  if (!Array.isArray(data) || data.length === 0) return false
  const sample = data.slice(0, 3)
  return sample.every(
    (item: any) =>
      item &&
      typeof item.timestamp === 'string' &&
      typeof item.cloud_run_service === 'string'
  )
}

export function extractDebugPrompt(markdown: string): string | null {
  const sectionMatch = markdown.match(/\*{3,}\s*\n([\s\S]*?)(?:\*{3,}|$)/)
  if (sectionMatch && sectionMatch[1].length > 100) {
    return sectionMatch[1].trim()
  }
  const promptSection = markdown.match(/###\s+Prompt[^\n]*\n([\s\S]*?)(?=\n###|\n\*{3,}|$)/i)
  if (promptSection && promptSection[1].length > 80) {
    return promptSection[1].trim()
  }
  return null
}

function extractConsultantCards(steps: any[]): any[] | null {
  if (!steps || steps.length === 0) return null
  const semanticTools = [
    'search_candidates_multi_criteria',
    'search_best_candidates',
    'get_users_bulk',
    'list_users',
  ]
  for (let i = steps.length - 1; i >= 0; i--) {
    const step = steps[i]
    if (step.type === 'result' && i > 0) {
      const callStep = steps[i - 1]
      if (callStep?.type === 'call' && semanticTools.includes(callStep.tool)) {
        const raw = step.data?.result?.[0]?.text || step.data?.content?.[0]?.text
        if (raw && looksLikeJson(raw)) {
          try {
            const parsed = JSON.parse(raw)
            const arr = Array.isArray(parsed) ? parsed : parsed.items || []
            if (arr.length > 0 && (arr[0].user_id || arr[0].id) && arr[0].full_name) {
              return arr.map((u: any) => ({ ...u, user_id: u.user_id ?? u.id }))
            }
          } catch (_) { /* ignore */ }
        }
      }
    }
  }
  return null
}

function unwrapToolData(toolData: any): any[] {
  if (!toolData) return []
  const envelope = toolData.result || toolData.content
  if (typeof toolData === 'object' && Array.isArray(envelope)) {
    const textItem = envelope.find((r: any) => r.type === 'text' && r.text)
    if (textItem) {
      const raw: string = textItem.text
      if (looksLikeJson(raw)) {
        try {
          const parsed = JSON.parse(raw)
          if (!Array.isArray(parsed) && parsed.items && Array.isArray(parsed.items)) {
            return parsed.items
          }
          if (!Array.isArray(parsed) && isNumericKeyMap(parsed)) {
            return []
          }
          return Array.isArray(parsed) ? parsed : [parsed]
        } catch (e) {
          console.warn('[unwrapToolData] JSON.parse failed:', e)
          return [{ _rawText: raw }]
        }
      }
      return [{ _rawText: raw }]
    }
    return [toolData]
  }
  if (typeof toolData === 'object' && toolData.items) return toolData.items
  if (Array.isArray(toolData)) return toolData
  return [toolData]
}

/** Message de bienvenue par défaut de l'assistant. */
function welcomeMessage(): Message {
  return {
    role: 'assistant',
    content: "Bonjour ! Je suis l'Assistant Opérationnel de Zenika. Je peux vous aider à rechercher des profils, analyser des compétences, ou gérer le catalogue d'équipements.",
    activeTab: 'preview',
  }
}

/** Crée un objet ChatSession runtime vide avec un message de bienvenue. */
function makeRuntimeSession(meta: ChatSession): ChatSession {
  return {
    ...meta,
    messages: [welcomeMessage()],
    isTyping: false,
    isLoadingHistory: false,
    historyLoaded: false,
  }
}

/** Applique la post-processing des messages d'historique (réhydratation). */
function rehydrateHistoryMessage(msg: Message): Message {
  if (msg.role !== 'assistant') return msg

  const hasMcpEnvelope = msg.data && typeof msg.data === 'object' && Array.isArray(msg.data.result)
  const missingParsedData = !msg.parsedData || msg.parsedData.length === 0
  const parsedDataIsStillMcpEnvelope =
    !missingParsedData &&
    Array.isArray(msg.parsedData) &&
    msg.parsedData.length > 0 &&
    typeof msg.parsedData[0] === 'object' &&
    Array.isArray((msg.parsedData[0] as any)?.result)

  if (msg.data && (missingParsedData || parsedDataIsStillMcpEnvelope) && hasMcpEnvelope) {
    const unwrapped = unwrapToolData(msg.data)
    if (unwrapped.length > 0) {
      msg.parsedData = unwrapped
      if (!msg.displayType || msg.displayType === 'text_only') msg.displayType = 'cards'
    }
  }

  if (msg.parsedData && Array.isArray(msg.parsedData) && isCloudRunLogs(msg.parsedData)) {
    msg.displayType = 'cloudrun_logs'
  }

  if (!msg.debugPrompt) {
    const markdownSource = msg.rawResponse || msg.content || ''
    const debugPrompt = extractDebugPrompt(markdownSource)
    if (debugPrompt) {
      msg.debugPrompt = debugPrompt
      if (!msg.rawResponse) {
        msg.content = msg.content.replace(/\*{3,}[\s\S]*?(?:\*{3,}|$)/, '').trim()
      }
    }
  }

  if (!msg.consultantCards && msg.steps && msg.steps.length > 0) {
    const cards = extractConsultantCards(msg.steps)
    if (cards) msg.consultantCards = cards
  }

  if (
    msg.data &&
    msg.data.dataType === 'competency' &&
    Array.isArray(msg.parsedData) &&
    msg.displayType === 'tree'
  ) {
    msg.parsedData = treeify(msg.parsedData)
  }

  if (!msg.activeTab) msg.activeTab = 'preview'
  return msg
}


// ── Store ────────────────────────────────────────────────────────────────────

export const useChatStore = defineStore('chat', {
  state: () => ({
    sessions: [] as ChatSession[],
    activeSessionId: null as string | null,
    isLoadingSessions: false,
  }),

  getters: {
    activeSession(state): ChatSession | null {
      if (!state.activeSessionId) return null
      return state.sessions.find(s => s.id === state.activeSessionId) ?? null
    },
    messages(): Message[] {
      return this.activeSession?.messages ?? [welcomeMessage()]
    },
    isTyping(): boolean {
      return this.activeSession?.isTyping ?? false
    },
    isLoadingHistory(): boolean {
      return this.activeSession?.isLoadingHistory ?? false
    },
  },

  actions: {
    // ── Session lifecycle ───────────────────────────────────────────────────

    async loadSessions() {
      this.isLoadingSessions = true
      try {
        const { sessions } = await agentApi.listSessions()
        this.sessions = sessions.map(s => makeRuntimeSession(s))
        // Active la première session par défaut
        if (this.sessions.length > 0 && !this.activeSessionId) {
          this.activeSessionId = this.sessions[0].id
        }
        // Charger l'historique de la session active immédiatement
        if (this.activeSessionId) {
          await this.fetchHistory(this.activeSessionId)
        }
      } catch (e) {
        console.warn('[chatStore] Could not load sessions', e)
      } finally {
        this.isLoadingSessions = false
      }
    },

    async createSession(name?: string) {
      const uxStore = useUxStore()
      if (this.sessions.length >= 10) {
        uxStore.showToast('Limite de 10 sessions atteinte. Supprimez une session.', 'error')
        return
      }
      try {
        const newMeta = await agentApi.createSession(name)
        this.sessions.push(makeRuntimeSession(newMeta))
        this.activeSessionId = newMeta.id
      } catch (e: any) {
        uxStore.showToast(
          e?.response?.data?.detail || 'Impossible de créer la session',
          'error'
        )
      }
    },

    async switchSession(id: string) {
      this.activeSessionId = id
      const session = this.sessions.find(s => s.id === id)
      if (session && !session.historyLoaded) {
        await this.fetchHistory(id)
      }
    },

    async renameSession(id: string, name: string) {
      const uxStore = useUxStore()
      try {
        await agentApi.renameSession(id, name)
        const session = this.sessions.find(s => s.id === id)
        if (session) session.name = name
      } catch (e: any) {
        uxStore.showToast(
          e?.response?.data?.detail || 'Impossible de renommer la session',
          'error'
        )
      }
    },

    async deleteSession(id: string) {
      const uxStore = useUxStore()
      if (this.sessions.length <= 1) {
        uxStore.showToast('Impossible de supprimer la dernière session.', 'error')
        return
      }
      try {
        await agentApi.deleteSession(id)
        const idx = this.sessions.findIndex(s => s.id === id)
        this.sessions.splice(idx, 1)
        // Switcher vers une autre session si on vient de supprimer l'active
        if (this.activeSessionId === id) {
          const next = this.sessions[idx > 0 ? idx - 1 : 0]
          if (next) await this.switchSession(next.id)
        }
        uxStore.showToast('Session supprimée', 'success')
      } catch (e: any) {
        uxStore.showToast(
          e?.response?.data?.detail || 'Impossible de supprimer la session',
          'error'
        )
      }
    },

    // ── Messages ────────────────────────────────────────────────────────────

    addMessage(msg: Message) {
      const session = this.sessions.find(s => s.id === this.activeSessionId)
      if (!session) return
      if (!msg.activeTab) msg.activeTab = 'preview'
      if (!session.messages) session.messages = []
      session.messages.push(msg)
    },

    async sendQuery(queryText: string) {
      if (!queryText.trim()) return
      const uxStore = useUxStore()
      const session = this.sessions.find(s => s.id === this.activeSessionId)
      if (!session) return

      this.addMessage({ role: 'user', content: queryText })
      session.isTyping = true

      try {
        const responseData = await agentApi.query(queryText, this.activeSessionId)
        let replyText = responseData.response || ''
        let displayType = 'text_only'
        let parsedData = null
        const toolData = responseData.data || null
        const steps = responseData.steps || []

        if (responseData.display_type) {
          displayType = responseData.display_type
        }

        try {
          const jsonMatch = replyText.match(/\{[\s\S]*\}/)
          if (jsonMatch) {
            const jsonObj = JSON.parse(jsonMatch[0].trim())
            if (jsonObj.reply && jsonObj.display_type) {
              replyText = jsonObj.reply
              displayType = jsonObj.display_type
              if (displayType === 'profile') displayType = 'cards'
              if (jsonObj.display_type === 'tree') {
                parsedData = jsonObj.data
              } else if (jsonObj.data) {
                parsedData = Array.isArray(jsonObj.data) ? jsonObj.data : [jsonObj.data]
              }
            }
          }
        } catch (e) {
          console.warn('Soft fail on JSON parsing', e)
        }

        if (!parsedData && toolData) {
          parsedData = unwrapToolData(toolData)
          if (displayType === 'text_only') displayType = 'cards'
        }

        if (parsedData && isCloudRunLogs(parsedData)) {
          displayType = 'cloudrun_logs'
        }

        if (toolData && toolData.dataType === 'competency' && Array.isArray(parsedData)) {
          parsedData = treeify(parsedData)
          displayType = 'tree'
        }

        const debugPrompt = extractDebugPrompt(replyText)
        if (debugPrompt) {
          replyText = replyText.replace(/\*{3,}[\s\S]*?(?:\*{3,}|$)/, '').trim()
        }

        const consultantCards = extractConsultantCards(steps)

        if (responseData.response) {
          if (responseData.degraded) {
            uxStore.showToast(
              '⚠️ Réponse partielle — un sous-agent est temporairement indisponible',
              'warning'
            )
          }
          this.addMessage({
            role: 'assistant',
            content: replyText,
            data: toolData,
            parsedData: parsedData,
            displayType: displayType,
            steps: steps,
            consultantCards: consultantCards || undefined,
            thoughts: responseData.thoughts || '',
            rawResponse: responseData.response,
            activeTab: 'preview',
            pagination: { currentPage: 1, itemsPerPage: 10 },
            usage: responseData.usage,
            semanticCacheHit: responseData.semantic_cache_hit === true,
            debugPrompt: debugPrompt || undefined,
          })
        } else {
          this.addMessage({
            role: 'assistant',
            content: JSON.stringify(responseData, null, 2),
            activeTab: 'expert',
          })
        }
      } catch (error: any) {
        uxStore.showToast(`Erreur: ${error.response?.data?.detail || error.message}`, 'error')
      } finally {
        session.isTyping = false
      }
    },

    async applyTree(treeData: any) {
      const uxStore = useUxStore()
      const session = this.sessions.find(s => s.id === this.activeSessionId)
      if (!session) return
      session.isTyping = true
      try {
        const responseData = await agentApi.query(
          `Applique cette taxonomie de compétences : ${JSON.stringify(treeData)}`,
          this.activeSessionId
        )
        this.addMessage({
          role: 'assistant',
          content: responseData.response || '',
          displayType: 'text_only',
          activeTab: 'preview',
        })
        uxStore.showToast('Taxonomie appliquée avec succès', 'success')
      } catch (error: any) {
        uxStore.showToast(
          `Erreur lors de l'application: ${error.response?.data?.detail || error.message}`,
          'error'
        )
      } finally {
        session.isTyping = false
      }
    },

    async fetchHistory(sessionId?: string) {
      const id = sessionId ?? this.activeSessionId
      if (!id) return
      const session = this.sessions.find(s => s.id === id)
      if (!session) return

      const uxStore = useUxStore()
      session.isLoadingHistory = true
      try {
        const response = await agentApi.history(id)
        if (response.history && response.history.length > 0) {
          session.messages = response.history.map(rehydrateHistoryMessage)
        } else {
          session.messages = [welcomeMessage()]
        }
        session.historyLoaded = true
      } catch (e) {
        console.warn('Could not load agent history', e)
        uxStore.showToast("Impossible de charger l'historique de conversation", 'error')
        session.messages = [welcomeMessage()]
      } finally {
        session.isLoadingHistory = false
      }
    },

    async resetHistory() {
      const uxStore = useUxStore()
      try {
        await agentApi.resetHistory(this.activeSessionId)
        const session = this.sessions.find(s => s.id === this.activeSessionId)
        if (session) {
          session.messages = [welcomeMessage()]
          session.historyLoaded = false
        }
        uxStore.showToast('Historique effacé', 'success')
      } catch (e) {
        uxStore.showToast("Impossible de réinitialiser l'historique", 'error')
      }
    },
  },
})
