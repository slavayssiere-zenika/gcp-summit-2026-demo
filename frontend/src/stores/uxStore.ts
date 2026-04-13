import { defineStore } from 'pinia'

interface Toast {
  id: number
  message: string
  type: 'success' | 'error' | 'info'
}

export const useUxStore = defineStore('ux', {
  state: () => ({
    toasts: [] as Toast[],
    toastIdCounter: 0
  }),
  actions: {
    showToast(message: string, type: 'success' | 'error' | 'info' = 'info') {
      const id = this.toastIdCounter++
      this.toasts.push({ id, message, type })
      
      // Auto-remove after 5 seconds
      setTimeout(() => {
        this.removeToast(id)
      }, 5000)
    },
    removeToast(id: number) {
      this.toasts = this.toasts.filter(t => t.id !== id)
    }
  }
})
