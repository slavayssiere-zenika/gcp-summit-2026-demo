import axios from 'axios'
import type { AgentQueryResponse, Message } from '@/types'

export const agentApi = {
  async query(queryText: string): Promise<AgentQueryResponse> {
    const locale = localStorage.getItem('zenika_locale') || 'fr'
    const token = localStorage.getItem('access_token')
    const headers: Record<string, string> = {
      'X-Preferred-Language': locale,
    }
    if (token) headers['Authorization'] = `Bearer ${token}`
    const response = await axios.post('/api/query', { query: queryText }, { headers })
    return response.data as AgentQueryResponse
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
