import { defineStore } from 'pinia'
import type { Message } from '@/types'
import { agentApi } from '@/services/agentApi'
import { treeify } from '@/utils/treeify'
import { useUxStore } from './uxStore'

/**
 * Unwrap MCP envelope format: { result: [{ type: "text", text: "<JSON string>" }] }
 * Sub-agents return data wrapped in this MCP protocol structure.
 * Falls back gracefully to generic array/object handling.
 *
 * Guards against non-JSON text values (e.g. "Consumption logged successfully.").
 */
function looksLikeJson(s: string): boolean {
  const trimmed = s.trimStart()
  return trimmed.startsWith('{') || trimmed.startsWith('[')
}

function unwrapToolData(toolData: any): any[] {
  if (!toolData) return []

  // MCP envelope: { result: [{ type: "text", text: "..." }] }
  if (typeof toolData === 'object' && Array.isArray(toolData.result)) {
    const textItem = toolData.result.find((r: any) => r.type === 'text' && r.text)
    if (textItem) {
      const raw: string = textItem.text
      if (looksLikeJson(raw)) {
        try {
          const parsed = JSON.parse(raw)
          return Array.isArray(parsed) ? parsed : [parsed]
        } catch (e) {
          // Malformed JSON — surface raw text as a readable string item
          console.warn('[unwrapToolData] JSON.parse failed on seemingly JSON-like string:', e)
          return [{ _rawText: raw }]
        }
      }
      // Plain-text result (e.g. "Consumption logged successfully.") — keep as-is
      return [{ _rawText: raw }]
    }
    // No text item found — return wrapping object itself
    return [toolData]
  }

  // Standard formats
  if (typeof toolData === 'object' && toolData.items) return toolData.items
  if (Array.isArray(toolData)) return toolData
  return [toolData]
}

export const useChatStore = defineStore('chat', {
  state: () => ({
    messages: [
      {
        role: 'assistant',
        content: "Bonjour ! Je suis l'Assistant Opérationnel de Zenika. Je peux vous aider à rechercher des profils, analyser des compétences, ou gérer le catalogue d'équipements.",
        activeTab: 'preview' as const
      }
    ] as Message[],
    isTyping: false
  }),
  actions: {
    addMessage(msg: Message) {
      if (!msg.activeTab) msg.activeTab = 'preview'
      this.messages.push(msg)
    },

    async sendQuery(queryText: string) {
      if (!queryText.trim()) return

      const uxStore = useUxStore()
      this.addMessage({ role: 'user', content: queryText })
      this.isTyping = true

      try {
        const responseData = await agentApi.query(queryText)
        let replyText = responseData.response || ''
        let displayType = 'text_only'
        let parsedData = null
        const toolData = responseData.data || null
        const steps = responseData.steps || []

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

        if (toolData && toolData.dataType === 'competency' && Array.isArray(parsedData)) {
          parsedData = treeify(parsedData)
          displayType = 'tree'
        }

        if (responseData.response) {
          this.addMessage({
            role: 'assistant',
            content: replyText,
            data: toolData,
            parsedData: parsedData,
            displayType: displayType,
            steps: steps,
            thoughts: responseData.thoughts || '',
            rawResponse: responseData.response,
            activeTab: 'preview',
            pagination: { currentPage: 1, itemsPerPage: 10 },
            usage: responseData.usage
          })
        } else {
          this.addMessage({
            role: 'assistant',
            content: JSON.stringify(responseData, null, 2),
            activeTab: 'expert'
          })
        }
      } catch (error: any) {
        uxStore.showToast(`Erreur: ${error.response?.data?.detail || error.message}`, 'error')
      } finally {
        this.isTyping = false
      }
    },

    async applyTree(treeData: any) {
      const uxStore = useUxStore()
      this.isTyping = true
      try {
        const responseData = await agentApi.query(`Applique cette taxonomie de compétences : ${JSON.stringify(treeData)}`)
        this.addMessage({
          role: 'assistant',
          content: responseData.response || '',
          displayType: 'text_only',
          activeTab: 'preview'
        })
        uxStore.showToast('Taxonomie appliquée avec succès', 'success')
      } catch (error: any) {
        uxStore.showToast(`Erreur lors de l'application: ${error.response?.data?.detail || error.message}`, 'error')
      } finally {
        this.isTyping = false
      }
    },

    async fetchHistory() {
      this.isTyping = true
      try {
        const response = await agentApi.history()
        if (response.history && response.history.length > 0) {
          this.messages = response.history.map((msg: Message) => {
            // Re-apply MCP unwrapping: history messages have raw `data` but no `parsedData`
            // because parsedData is computed client-side and not persisted in Redis.
            // Force re-derive when data is MCP envelope { result: [...] } to fix stale Redis cache.
            // Only re-derive parsedData when it is genuinely absent/empty.
            // Do NOT force re-unwrap when parsedData is already populated: it was
            // either set by the backend or by a previous client-side pass, and
            // double-processing causes spurious JSON.parse errors on plain-text MCP
            // results like "Consumption logged successfully.".
            const hasMcpEnvelope = msg.data && typeof msg.data === 'object' && Array.isArray(msg.data.result)
            const missingParsedData = !msg.parsedData || msg.parsedData.length === 0
            if (msg.data && missingParsedData && hasMcpEnvelope) {
              const unwrapped = unwrapToolData(msg.data)
              if (unwrapped.length > 0) {
                msg.parsedData = unwrapped
                if (!msg.displayType || msg.displayType === 'text_only') msg.displayType = 'cards'
              }
            }

            if (msg.data && msg.data.dataType === 'competency' && Array.isArray(msg.parsedData) && msg.displayType === 'tree') {
              msg.parsedData = treeify(msg.parsedData)
            }
            if (!msg.activeTab) msg.activeTab = 'preview'
            return msg
          })
        }
      } catch (e) {
        console.warn('Could not load agent history', e)
      } finally {
        this.isTyping = false
      }
    },

    async resetHistory() {
      const uxStore = useUxStore()
      try {
        await agentApi.resetHistory()
        this.messages = [
          {
            role: 'assistant',
            content: "Bonjour ! Je suis l'Assistant Opérationnel de Zenika. Je peux vous aider à rechercher des profils, analyser des compétences, ou gérer le catalogue d'équipements.",
            activeTab: 'preview'
          }
        ]
        uxStore.showToast('Historique effacé', 'success')
      } catch (e) {
        uxStore.showToast("Impossible de réinitialiser l'historique", 'error')
      }
    }
  }
})
