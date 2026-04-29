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

/**
 * Détecte si un tableau de données correspond à des logs Cloud Run structurés.
 * Un log Cloud Run a: timestamp + cloud_run_service + (message | severity)
 */
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

/**
 * Détecte si le texte de réponse markdown contient un prompt de débogage suggéré.
 * L'agent ops génère typiquement des sections avec blockquotes `>` et des titres ###.
 */
export function extractDebugPrompt(markdown: string): string | null {
  // Cherche une section de prompt entre *** ou --- délimiteurs
  const sectionMatch = markdown.match(/\*{3,}\s*\n([\s\S]*?)(?:\*{3,}|$)/)
  if (sectionMatch && sectionMatch[1].length > 100) {
    return sectionMatch[1].trim()
  }
  // Cherche une section ### Prompt
  const promptSection = markdown.match(/###\s+Prompt[^\n]*\n([\s\S]*?)(?=\n###|\n\*{3,}|$)/i)
  if (promptSection && promptSection[1].length > 80) {
    return promptSection[1].trim()
  }
  return null
}

/**
 * Extrait les résultats de recherche sémantique de consultants depuis les steps de l'agent.
 * Cherche le résultat du dernier appel à search_candidates_multi_criteria ou search_best_candidates.
 * Retourne null si aucun résultat sémantique trouvé.
 */
function extractConsultantCards(steps: any[]): any[] | null {
  if (!steps || steps.length === 0) return null
  const semanticTools = ['search_candidates_multi_criteria', 'search_best_candidates']
  // Parcourir en sens inverse pour prendre le dernier résultat
  for (let i = steps.length - 1; i >= 0; i--) {
    const step = steps[i]
    if (step.type === 'result' && i > 0) {
      const callStep = steps[i - 1]
      if (callStep?.type === 'call' && semanticTools.includes(callStep.tool)) {
        const raw = step.data?.result?.[0]?.text
        if (raw && looksLikeJson(raw)) {
          try {
            const parsed = JSON.parse(raw)
            const arr = Array.isArray(parsed) ? parsed : parsed.items || []
            // Valider que c'est bien des consultants (user_id + full_name + combined_similarity ou source_tag)
            if (arr.length > 0 && arr[0].user_id && (arr[0].full_name || arr[0].combined_similarity !== undefined)) {
              return arr
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

  // MCP envelope: { result: [{ type: "text", text: "..." }] }
  if (typeof toolData === 'object' && Array.isArray(toolData.result)) {
    const textItem = toolData.result.find((r: any) => r.type === 'text' && r.text)
    if (textItem) {
      const raw: string = textItem.text
      if (looksLikeJson(raw)) {
        try {
          const parsed = JSON.parse(raw)
          // Paginated MCP responses: { items: [...], total, skip, limit }
          if (!Array.isArray(parsed) && parsed.items && Array.isArray(parsed.items)) {
            return parsed.items
          }
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
    isTyping: false,
    isLoadingHistory: false
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

        // Détection logs Cloud Run — prioritaire sur les cards génériques
        if (parsedData && isCloudRunLogs(parsedData)) {
          displayType = 'cloudrun_logs'
        }

        if (toolData && toolData.dataType === 'competency' && Array.isArray(parsedData)) {
          parsedData = treeify(parsedData)
          displayType = 'tree'
        }

        // Détection prompt de débogage dans la réponse markdown
        const debugPrompt = extractDebugPrompt(replyText)
        if (debugPrompt) {
          replyText = replyText.replace(/\*{3,}[\s\S]*?(?:\*{3,}|$)/, '').trim()
        }

        // Extraction des cards consultants depuis les steps sémantiques (dual display)
        const consultantCards = extractConsultantCards(steps)

        if (responseData.response) {
          // ADR12-4 — Alerte si le sous-agent répond en mode dégradé (erreur réseau A2A)
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
            debugPrompt: debugPrompt || undefined
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
      const uxStore = useUxStore()
      this.isLoadingHistory = true
      try {
        const response = await agentApi.history()
        if (response.history && response.history.length > 0) {
          this.messages = response.history.map((msg: Message) => {
            if (msg.role !== 'assistant') return msg

            const hasMcpEnvelope = msg.data && typeof msg.data === 'object' && Array.isArray(msg.data.result)
            const missingParsedData = !msg.parsedData || msg.parsedData.length === 0

            // Detect when parsedData was persisted in Redis still wrapped in MCP envelope format:
            // parsedData = [{ result: [{ type: "text", text: "<JSON string>" }] }]
            // This happens when the Redis session stores msg.parsedData before client-side unwrapping.
            const parsedDataIsStillMcpEnvelope = !missingParsedData &&
              Array.isArray(msg.parsedData) &&
              msg.parsedData.length > 0 &&
              typeof msg.parsedData[0] === 'object' &&
              Array.isArray((msg.parsedData[0] as any)?.result)

            // Re-unwrap if: parsedData is absent OR still in raw MCP envelope format
            if (msg.data && (missingParsedData || parsedDataIsStillMcpEnvelope) && hasMcpEnvelope) {
              const unwrapped = unwrapToolData(msg.data)
              if (unwrapped.length > 0) {
                msg.parsedData = unwrapped
                if (!msg.displayType || msg.displayType === 'text_only') msg.displayType = 'cards'
              }
            }

            // ── Re-apply intelligent display type detection (same logic as sendQuery) ──
            // The backend persists displayType='cards' for all data messages. We must
            // re-detect Cloud Run logs and debug prompts on every history load.
            if (msg.parsedData && Array.isArray(msg.parsedData) && isCloudRunLogs(msg.parsedData)) {
              msg.displayType = 'cloudrun_logs'
            }

            // Re-extract debug prompt from rawResponse or content if not already set
            if (!msg.debugPrompt) {
              const markdownSource = msg.rawResponse || msg.content || ''
              const debugPrompt = extractDebugPrompt(markdownSource)
              if (debugPrompt) {
                msg.debugPrompt = debugPrompt
                // Strip the *** ... *** block from the visible content (same as sendQuery)
                if (!msg.rawResponse) {
                  // rawResponse was not stored — strip from content directly
                  msg.content = msg.content.replace(/\*{3,}[\s\S]*?(?:\*{3,}|$)/, '').trim()
                }
              }
            }

            // Re-extract consultant cards from steps on history reload
            if (!msg.consultantCards && msg.steps && msg.steps.length > 0) {
              const cards = extractConsultantCards(msg.steps)
              if (cards) msg.consultantCards = cards
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
        uxStore.showToast("Impossible de charger l'historique de conversation", 'error')
      } finally {
        this.isLoadingHistory = false
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
