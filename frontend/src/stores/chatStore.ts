import { defineStore } from 'pinia'
import type { Message } from '@/types'
import { agentApi } from '@/services/agentApi'
import { treeify } from '@/utils/treeify'
import { useUxStore } from './uxStore'

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
          const jsonMatch = replyText.match(/\{[\s\S]*\}/);
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
          console.warn("Soft fail on JSON parsing", e)
        }

        if (!parsedData && toolData) {
          if (typeof toolData === 'object' && toolData.items) {
            parsedData = toolData.items
          } else if (Array.isArray(toolData)) {
            parsedData = toolData
          } else {
            parsedData = [toolData]
          }
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
            if (msg.data && msg.data.dataType === 'competency' && Array.isArray(msg.parsedData) && msg.displayType === 'tree') {
              msg.parsedData = treeify(msg.parsedData);
            }
            if (!msg.activeTab) msg.activeTab = 'preview';
            return msg;
          })
        }
      } catch(e) {
        console.warn("Could not load agent history", e)
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
      } catch(e) {
        uxStore.showToast("Impossible de réinitialiser l'historique", 'error')
      }
    }
  }
})
