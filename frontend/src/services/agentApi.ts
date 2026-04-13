import axios from 'axios'
import type { Message } from '@/types'

export const agentApi = {
  async query(queryText: string): Promise<any> {
    const response = await axios.post('/api/query', { query: queryText })
    return response.data
  },

  async history(): Promise<{ history: Message[] }> {
    const response = await axios.get('/api/history')
    return response.data
  },

  async resetHistory(): Promise<void> {
    const token = localStorage.getItem('access_token')
    await axios.delete('/api/history', {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
  }
}
