import axios from 'axios'
import type { AgentQueryResponse, ChatSession, Message } from '@/types'

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('access_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export const agentApi = {
  async query(queryText: string, sessionId?: string | null): Promise<AgentQueryResponse> {
    const locale = localStorage.getItem('zenika_locale') || 'fr'
    const headers: Record<string, string> = {
      'X-Preferred-Language': locale,
      ...authHeaders(),
    }
    const body: Record<string, any> = { query: queryText }
    if (sessionId) body.session_id = sessionId
    const response = await axios.post('/api/query', body, { headers })
    return response.data as AgentQueryResponse
  },

  async history(sessionId?: string | null): Promise<{ history: Message[] }> {
    const params = sessionId ? { session_id: sessionId } : {}
    const response = await axios.get('/api/history', {
      headers: authHeaders(),
      params,
    })
    return response.data
  },

  async resetHistory(sessionId?: string | null): Promise<void> {
    const params = sessionId ? { session_id: sessionId } : {}
    await axios.delete('/api/history', {
      headers: authHeaders(),
      params,
    })
  },

  // ── Session management ────────────────────────────────────────────────────

  async listSessions(): Promise<{ sessions: ChatSession[] }> {
    const response = await axios.get('/api/sessions', { headers: authHeaders() })
    return response.data
  },

  async createSession(name?: string): Promise<ChatSession> {
    const response = await axios.post(
      '/api/sessions',
      { name: name || 'Nouvelle session' },
      { headers: authHeaders() }
    )
    return response.data as ChatSession
  },

  async renameSession(sessionId: string, name: string): Promise<void> {
    await axios.patch(
      `/api/sessions/${encodeURIComponent(sessionId)}`,
      { name },
      { headers: authHeaders() }
    )
  },

  async deleteSession(sessionId: string): Promise<void> {
    await axios.delete(`/api/sessions/${encodeURIComponent(sessionId)}`, {
      headers: authHeaders(),
    })
  },

  /**
   * Phase 3 HITL — Envoie la décision humaine (approved/rejected) pour un pending staffing.
   * Routé via /api/hitl/respond → agent_missions_api (via Nginx + LB).
   */
  async hitlRespond(
    hitlId: string,
    decision: 'approved' | 'rejected',
    comment = '',
  ): Promise<{ success: boolean; message: string }> {
    const response = await axios.post(
      '/api/hitl/respond',
      { hitl_id: hitlId, decision, comment },
      { headers: authHeaders() },
    )
    return response.data
  },

  /**
   * Phase 3 HITL — Liste les demandes d'approbation en attente pour l'utilisateur courant.
   */
  async hitlPending(): Promise<{ pending: any[] }> {
    const response = await axios.get('/api/hitl/pending', { headers: authHeaders() })
    return response.data
  },
}
